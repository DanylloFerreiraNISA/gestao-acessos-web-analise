from pathlib import Path
import py_compile

ROOT = Path.cwd()
APP = ROOT / 'app'
T = APP / 'templates'
S = APP / 'static'
for p in (APP, T, S): p.mkdir(parents=True, exist_ok=True)

MODULE = r'''from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, delete, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, selectinload

from app.database import Base, engine, get_database_session
from app.models import Acesso, Departamento, Funcionario, FuncionarioPerfil, Perfil, PerfilAcesso

router = APIRouter()
templates = Jinja2Templates(directory='app/templates')
Db = Annotated[Session, Depends(get_database_session)]

ROLE_ADMIN = 'ADMIN_TI'
ROLE_MANAGER = 'GESTOR_DEPARTAMENTO'
ROLE_ANALYST = 'ANALISTA_TI'
PROPOSAL_STATUSES = {'RASCUNHO', 'EM_REVISAO', 'DEVOLVIDO', 'APROVADO', 'REJEITADO', 'PUBLICADO', 'ARQUIVADO'}
PROPOSAL_ORIGINS = {'CRIADO_VAZIO', 'COPIADO_DE_PERFIL', 'CONSOLIDADO_FUNCIONARIO', 'CONSOLIDADO_DEPARTAMENTO_COMUM', 'CONSOLIDADO_DEPARTAMENTO_UNIAO'}


class SystemUser(Base):
    __tablename__ = 'system_users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default=ROLE_MANAGER)
    department_id: Mapped[int | None] = mapped_column(ForeignKey('departamentos.id'), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey('funcionarios.id'))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    department: Mapped[Departamento | None] = relationship()
    employee: Mapped[Funcionario | None] = relationship()


class ProfileProposal(Base):
    __tablename__ = 'profile_proposals'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    justification: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[int] = mapped_column(ForeignKey('departamentos.id'), index=True, nullable=False)
    origin: Mapped[str] = mapped_column(String(60), nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(30), nullable=False, default='RASCUNHO')
    source_profile_id: Mapped[int | None] = mapped_column(ForeignKey('perfis.id'))
    source_employee_id: Mapped[int | None] = mapped_column(ForeignKey('funcionarios.id'))
    created_by_id: Mapped[int] = mapped_column(ForeignKey('system_users.id'), nullable=False)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey('system_users.id'))
    imported_result_profile_id: Mapped[int | None] = mapped_column(ForeignKey('perfis.id'))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    department: Mapped[Departamento] = relationship(foreign_keys=[department_id])
    source_profile: Mapped[Perfil | None] = relationship(foreign_keys=[source_profile_id])
    source_employee: Mapped[Funcionario | None] = relationship(foreign_keys=[source_employee_id])
    accesses: Mapped[list['ProfileProposalAccess']] = relationship(back_populates='proposal', cascade='all, delete-orphan')


class ProfileProposalAccess(Base):
    __tablename__ = 'profile_proposal_accesses'
    __table_args__ = (UniqueConstraint('proposal_id', 'access_id', name='uq_proposal_access'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey('profile_proposals.id', ondelete='CASCADE'), index=True)
    access_id: Mapped[int] = mapped_column(ForeignKey('acessos.id'), index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    proposal: Mapped[ProfileProposal] = relationship(back_populates='accesses')
    access: Mapped[Acesso] = relationship()


class ProposalHistory(Base):
    __tablename__ = 'proposal_history'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey('profile_proposals.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('system_users.id'))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('system_users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user: Mapped[SystemUser] = relationship()


def create_tables():
    Base.metadata.create_all(bind=engine)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
    return f'pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, expected = stored.split('$', 3)
        if scheme != 'pbkdf2_sha256': return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def current_user_optional(request: Request, session: Db) -> SystemUser | None:
    token = request.cookies.get('access_session')
    if not token: return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    login = session.scalar(select(LoginSession).options(selectinload(LoginSession.user)).where(LoginSession.token_hash == token_hash))
    if not login or login.expires_at <= datetime.now(timezone.utc) or not login.user.active: return None
    return login.user


def require_user(user: Annotated[SystemUser | None, Depends(current_user_optional)]) -> SystemUser:
    if not user: raise HTTPException(status_code=401, detail='Autenticacao obrigatoria')
    return user


def require_admin(user: Annotated[SystemUser, Depends(require_user)]) -> SystemUser:
    if user.role not in {ROLE_ADMIN, ROLE_ANALYST}: raise HTTPException(status_code=403, detail='Acesso restrito a T.I.')
    return user


def enforce_department(user: SystemUser, department_id: int):
    if user.role in {ROLE_ADMIN, ROLE_ANALYST}: return
    if user.department_id is None or user.department_id != department_id:
        raise HTTPException(status_code=403, detail='Acesso nao autorizado para este departamento')


def scoped_employee_query(user: SystemUser):
    query = select(Funcionario).options(selectinload(Funcionario.departamento)).order_by(Funcionario.nome)
    if user.role == ROLE_MANAGER:
        query = query.where(Funcionario.departamento_id == user.department_id)
    return query


def profile_ids_for_department(session: Session, department_id: int):
    return select(FuncionarioPerfil.perfil_id).join(Funcionario, Funcionario.id == FuncionarioPerfil.funcionario_id).where(Funcionario.departamento_id == department_id).distinct()


def proposal_access_map_from_profile(session: Session, profile_id: int):
    return {access_id: status for access_id, status in session.execute(select(PerfilAcesso.acesso_id, PerfilAcesso.status).where(PerfilAcesso.perfil_id == profile_id))}


def proposal_access_map_from_employee(session: Session, employee_id: int):
    rows = session.execute(select(PerfilAcesso.acesso_id, PerfilAcesso.status).join(FuncionarioPerfil, FuncionarioPerfil.perfil_id == PerfilAcesso.perfil_id).where(FuncionarioPerfil.funcionario_id == employee_id)).all()
    result = {}
    for access_id, access_status in rows:
        normalized = str(access_status or '').casefold()
        if normalized == 'permitido': result[access_id] = 'Permitido'
        elif access_id not in result and normalized == 'negado': result[access_id] = 'Negado'
    return result


def proposal_access_map_from_department(session: Session, department_id: int, mode: str):
    employees = session.scalars(select(Funcionario.id).where(Funcionario.departamento_id == department_id, Funcionario.ativo.is_(True))).all()
    if not employees: return {}
    maps = [proposal_access_map_from_employee(session, employee_id) for employee_id in employees]
    if mode == 'CONSOLIDADO_DEPARTAMENTO_COMUM':
        common = set(maps[0])
        for item in maps[1:]: common &= {access_id for access_id, value in item.items() if str(value).casefold() == 'permitido'}
        return {access_id: 'Permitido' for access_id in common if all(str(item.get(access_id, '')).casefold() == 'permitido' for item in maps)}
    result = {}
    for item in maps:
        for access_id, value in item.items():
            if str(value).casefold() == 'permitido': result[access_id] = 'Permitido'
            elif access_id not in result: result[access_id] = value
    return result


def create_history(session: Session, proposal_id: int, user_id: int, action: str, details: str | None = None):
    session.add(ProposalHistory(proposal_id=proposal_id, user_id=user_id, action=action, details=details))


@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request, user: Annotated[SystemUser | None, Depends(current_user_optional)]):
    if user: return RedirectResponse('/portal', status_code=303)
    return templates.TemplateResponse(request=request, name='login.html', context={'error': None})


@router.post('/login', response_class=HTMLResponse)
def login(request: Request, session: Db, email: Annotated[str, Form()], password: Annotated[str, Form()]):
    user = session.scalar(select(SystemUser).where(func.lower(SystemUser.email) == email.strip().lower()))
    if not user or not user.active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name='login.html', context={'error': 'E-mail ou senha invalidos'}, status_code=401)
    raw = secrets.token_urlsafe(48)
    session.add(LoginSession(token_hash=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id, expires_at=datetime.now(timezone.utc).replace(microsecond=0) + __import__('datetime').timedelta(hours=10)))
    session.commit()
    response = RedirectResponse('/portal', status_code=303)
    response.set_cookie('access_session', raw, httponly=True, samesite='lax', secure=False, max_age=36000)
    return response


@router.post('/logout')
def logout(request: Request, session: Db):
    token = request.cookies.get('access_session')
    if token:
        session.execute(delete(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        session.commit()
    response = RedirectResponse('/login', status_code=303)
    response.delete_cookie('access_session')
    return response


@router.get('/portal', response_class=HTMLResponse)
def portal(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    employee_count = session.scalar(select(func.count()).select_from(Funcionario).where(Funcionario.departamento_id == user.department_id)) if user.role == ROLE_MANAGER else session.scalar(select(func.count()).select_from(Funcionario))
    proposal_query = select(func.count()).select_from(ProfileProposal)
    if user.role == ROLE_MANAGER: proposal_query = proposal_query.where(ProfileProposal.department_id == user.department_id)
    return templates.TemplateResponse(request=request, name='portal.html', context={'user': user, 'employee_count': employee_count or 0, 'proposal_count': session.scalar(proposal_query) or 0})


@router.get('/portal/funcionarios', response_class=HTMLResponse)
def portal_employees(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    return templates.TemplateResponse(request=request, name='portal_employees.html', context={'user': user, 'employees': session.scalars(scoped_employee_query(user)).all()})


@router.get('/portal/funcionarios/{employee_id}', response_class=HTMLResponse)
def portal_employee_detail(request: Request, employee_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    employee = session.scalar(select(Funcionario).options(selectinload(Funcionario.departamento), selectinload(Funcionario.perfis).selectinload(FuncionarioPerfil.perfil)).where(Funcionario.id == employee_id))
    if not employee: raise HTTPException(404, 'Funcionario nao encontrado')
    enforce_department(user, employee.departamento_id)
    return templates.TemplateResponse(request=request, name='portal_employee.html', context={'user': user, 'employee': employee})


@router.get('/portal/propostas', response_class=HTMLResponse)
def proposals(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    query = select(ProfileProposal).options(selectinload(ProfileProposal.department)).order_by(ProfileProposal.created_at.desc())
    if user.role == ROLE_MANAGER: query = query.where(ProfileProposal.department_id == user.department_id)
    return templates.TemplateResponse(request=request, name='proposals.html', context={'user': user, 'proposals': session.scalars(query).all()})


@router.get('/portal/propostas/nova', response_class=HTMLResponse)
def proposal_new(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    employees = session.scalars(scoped_employee_query(user)).all()
    profile_query = select(Perfil).order_by(Perfil.nome)
    if user.role == ROLE_MANAGER: profile_query = profile_query.where(Perfil.id.in_(profile_ids_for_department(session, user.department_id)))
    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if user.role in {ROLE_ADMIN, ROLE_ANALYST} else [user.department]
    return templates.TemplateResponse(request=request, name='proposal_new.html', context={'user': user, 'employees': employees, 'profiles': session.scalars(profile_query).all(), 'departments': departments})


@router.post('/portal/propostas/nova')
def proposal_create(session: Db, user: Annotated[SystemUser, Depends(require_user)], name: Annotated[str, Form()], origin: Annotated[str, Form()], department_id: Annotated[int, Form()], description: Annotated[str, Form()] = '', justification: Annotated[str, Form()] = '', source_profile_id: Annotated[int | None, Form()] = None, source_employee_id: Annotated[int | None, Form()] = None):
    if origin not in PROPOSAL_ORIGINS: raise HTTPException(400, 'Origem invalida')
    enforce_department(user, department_id)
    if user.role == ROLE_MANAGER: department_id = user.department_id
    if source_employee_id:
        employee = session.get(Funcionario, source_employee_id)
        if not employee: raise HTTPException(404, 'Funcionario de origem nao encontrado')
        enforce_department(user, employee.departamento_id)
    if source_profile_id and user.role == ROLE_MANAGER:
        allowed = session.scalar(select(func.count()).select_from(FuncionarioPerfil).join(Funcionario).where(FuncionarioPerfil.perfil_id == source_profile_id, Funcionario.departamento_id == user.department_id))
        if not allowed: raise HTTPException(403, 'Perfil base fora do departamento')
    proposal = ProfileProposal(name=name.strip(), description=description.strip() or None, justification=justification.strip() or None, department_id=department_id, origin=origin, created_by_id=user.id, source_profile_id=source_profile_id, source_employee_id=source_employee_id)
    session.add(proposal); session.flush()
    access_map = {}
    if origin == 'COPIADO_DE_PERFIL' and source_profile_id: access_map = proposal_access_map_from_profile(session, source_profile_id)
    elif origin == 'CONSOLIDADO_FUNCIONARIO' and source_employee_id: access_map = proposal_access_map_from_employee(session, source_employee_id)
    elif origin in {'CONSOLIDADO_DEPARTAMENTO_COMUM', 'CONSOLIDADO_DEPARTAMENTO_UNIAO'}: access_map = proposal_access_map_from_department(session, department_id, origin)
    for access_id, access_status in access_map.items(): session.add(ProfileProposalAccess(proposal_id=proposal.id, access_id=access_id, status=access_status))
    create_history(session, proposal.id, user.id, 'CRIADA', f'Origem: {origin}')
    session.commit()
    return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)


@router.get('/portal/propostas/{proposal_id}', response_class=HTMLResponse)
def proposal_detail(request: Request, proposal_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    proposal = session.scalar(select(ProfileProposal).options(selectinload(ProfileProposal.department), selectinload(ProfileProposal.accesses).selectinload(ProfileProposalAccess.access)).where(ProfileProposal.id == proposal_id))
    if not proposal: raise HTTPException(404, 'Proposta nao encontrada')
    enforce_department(user, proposal.department_id)
    return templates.TemplateResponse(request=request, name='proposal_detail.html', context={'user': user, 'proposal': proposal})


@router.post('/portal/propostas/{proposal_id}/enviar')
def proposal_submit(proposal_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    proposal = session.get(ProfileProposal, proposal_id)
    if not proposal: raise HTTPException(404, 'Proposta nao encontrada')
    enforce_department(user, proposal.department_id)
    if proposal.workflow_status not in {'RASCUNHO', 'DEVOLVIDO'}: raise HTTPException(409, 'Estado nao permite envio')
    proposal.workflow_status = 'EM_REVISAO'; proposal.submitted_at = datetime.now(timezone.utc)
    create_history(session, proposal.id, user.id, 'ENVIADA_PARA_TI')
    session.commit(); return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)


@router.get('/admin/contas', response_class=HTMLResponse)
def accounts(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_admin)]):
    users = session.scalars(select(SystemUser).options(selectinload(SystemUser.department)).order_by(SystemUser.name)).all()
    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all()
    return templates.TemplateResponse(request=request, name='accounts.html', context={'user': user, 'users': users, 'departments': departments})


@router.post('/admin/contas')
def account_create(session: Db, user: Annotated[SystemUser, Depends(require_admin)], name: Annotated[str, Form()], email: Annotated[str, Form()], password: Annotated[str, Form()], role: Annotated[str, Form()], department_id: Annotated[int | None, Form()] = None):
    if role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_ANALYST}: raise HTTPException(400, 'Papel invalido')
    if role == ROLE_MANAGER and not department_id: raise HTTPException(400, 'Gestor precisa de departamento')
    session.add(SystemUser(name=name.strip(), email=email.strip().lower(), password_hash=hash_password(password), role=role, department_id=department_id, active=True))
    session.commit(); return RedirectResponse('/admin/contas', status_code=303)


@router.post('/admin/propostas/{proposal_id}/{action}')
def proposal_review(proposal_id: int, action: str, session: Db, user: Annotated[SystemUser, Depends(require_admin)], details: Annotated[str, Form()] = ''):
    proposal = session.get(ProfileProposal, proposal_id)
    if not proposal: raise HTTPException(404, 'Proposta nao encontrada')
    mapping = {'aprovar': 'APROVADO', 'rejeitar': 'REJEITADO', 'devolver': 'DEVOLVIDO'}
    if action not in mapping: raise HTTPException(400, 'Acao invalida')
    proposal.workflow_status = mapping[action]; proposal.reviewed_by_id = user.id; proposal.reviewed_at = datetime.now(timezone.utc)
    create_history(session, proposal.id, user.id, mapping[action], details.strip() or None)
    session.commit(); return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)
'''

(APP / 'access_control.py').write_text(MODULE, encoding='utf-8', newline='\n')

TEMPLATES_MAP = {
'login.html': '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><link rel="stylesheet" href="/static/portal.css"><title>Entrar</title></head><body class="login-body"><form class="login-card" method="post"><h1>Gestão de Acessos</h1><p>Entre com sua conta do sistema.</p>{% if error %}<div class="error">{{ error }}</div>{% endif %}<label>E-mail<input name="email" type="email" required></label><label>Senha<input name="password" type="password" required></label><button>Entrar</button></form></body></html>''',
'_portal_nav.html': '''<header class="portal-nav"><a href="/portal">Gestão de Acessos</a><nav><a href="/portal/funcionarios">Funcionários</a><a href="/portal/propostas">Propostas</a>{% if user.role in ['ADMIN_TI','ANALISTA_TI'] %}<a href="/admin/contas">Contas</a><a href="/comparar">Comparar</a>{% endif %}</nav><form method="post" action="/logout"><button>Sair</button></form></header>''',
'portal.html': '''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/portal.css"><title>Portal</title></head><body>{% include '_portal_nav.html' %}<main><section class="portal-hero"><h1>{{ user.name }}</h1><p>{{ user.role }}{% if user.department %} · {{ user.department.nome }}{% endif %}</p></section><section class="metrics"><article><span>Funcionários no escopo</span><strong>{{ employee_count }}</strong></article><article><span>Propostas no escopo</span><strong>{{ proposal_count }}</strong></article></section></main></body></html>''',
'portal_employees.html': '''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/portal.css"><title>Funcionários</title></head><body>{% include '_portal_nav.html' %}<main><h1>Funcionários{% if user.role == 'GESTOR_DEPARTAMENTO' %} · {{ user.department.nome }}{% endif %}</h1><div class="cards">{% for employee in employees %}<a href="/portal/funcionarios/{{ employee.id }}"><b>{{ employee.nome }}</b><span>{{ employee.login }}</span><small>{{ employee.departamento.nome if employee.departamento else 'Sem departamento' }}</small></a>{% else %}<p>Nenhum funcionário no seu escopo.</p>{% endfor %}</div></main></body></html>''',
'portal_employee.html': '''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/portal.css"><title>{{ employee.nome }}</title></head><body>{% include '_portal_nav.html' %}<main><a href="/portal/funcionarios">Voltar</a><h1>{{ employee.nome }}</h1><p>{{ employee.login }} · {{ employee.departamento.nome }}</p><h2>Perfis vinculados</h2><div class="chips">{% for link in employee.perfis %}<span>{{ link.perfil.nome }}</span>{% else %}<span>Nenhum perfil</span>{% endfor %}</div></main></body></html>''',
'proposals.html': '''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/portal.css"><title>Propostas</title></head><body>{% include '_portal_nav.html' %}<main><div class="title-row"><h1>Propostas de perfil</h1><a class="primary" href="/portal/propostas/nova">Nova proposta</a></div><div class="list">{% for p in proposals %}<a href="/portal/propostas/{{ p.id }}"><b>{{ p.name }}</b><span>{{ p.department.nome }} · {{ p.origin }}</span><em class="status {{ p.workflow_status|lower }}">{{ p.workflow_status }}</em></a>{% else %}<p>Nenhuma proposta.</p>{% endfor %}</div></main></body></html>''',
'proposal_new.html': '''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/portal.css"><title>Nova proposta</title></head><body>{% include '_portal_nav.html' %}<main><h1>Nova proposta de perfil</h1><form class="form-card" method="post"><label>Nome<input name="name" required></label><label>Departamento<select name="department_id" required>{% for d in departments %}<option value="{{ d.id }}">{{ d.nome }}</option>{% endfor %}</select></label><label>Como iniciar?<select name="origin" id="origin" required><option value="CRIADO_VAZIO">Perfil vazio</option><option value="COPIADO_DE_PERFIL">Copiar perfil existente</option><option value="CONSOLIDADO_FUNCIONARIO">Consolidado de funcionário</option><option value="CONSOLIDADO_DEPARTAMENTO_COMUM">Base comum do departamento</option><option value="CONSOLIDADO_DEPARTAMENTO_UNIAO">União do departamento, revisão obrigatória</option></select></label><label>Perfil base<select name="source_profile_id"><option value="">Não se aplica</option>{% for p in profiles %}<option value="{{ p.id }}">{{ p.nome }}</option>{% endfor %}</select></label><label>Funcionário base<select name="source_employee_id"><option value="">Não se aplica</option>{% for e in employees %}<option value="{{ e.id }}">{{ e.nome }}</option>{% endfor %}</select></label><label>Descrição<textarea name="description"></textarea></label><label>Justificativa<textarea name="justification"></textarea></label><div class="warning">A união pode juntar acessos excepcionais de pessoas diferentes. A T.I. deverá revisar antes da aprovação.</div><button>Criar proposta</button></form></main></body></html>''',
'proposal_detail.html': '''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/portal.css"><title>{{ proposal.name }}</title></head><body>{% include '_portal_nav.html' %}<main><a href="/portal/propostas">Voltar</a><h1>{{ proposal.name }}</h1><p>{{ proposal.department.nome }} · {{ proposal.origin }} · <b>{{ proposal.workflow_status }}</b></p><p>{{ proposal.description or '' }}</p><h2>Acessos da proposta ({{ proposal.accesses|length }})</h2><div class="access-list">{% for item in proposal.accesses %}<div><span>{{ item.access.caminho_completo }} › {{ item.access.tela_final }} › {{ item.access.botao }}</span><b class="permission {{ item.status|lower }}">{{ item.status }}</b></div>{% else %}<p>Proposta vazia.</p>{% endfor %}</div>{% if proposal.workflow_status in ['RASCUNHO','DEVOLVIDO'] %}<form method="post" action="/portal/propostas/{{ proposal.id }}/enviar"><button>Enviar para T.I.</button></form>{% endif %}{% if user.role in ['ADMIN_TI','ANALISTA_TI'] and proposal.workflow_status == 'EM_REVISAO' %}<section class="review"><form method="post" action="/admin/propostas/{{ proposal.id }}/aprovar"><textarea name="details" placeholder="Parecer"></textarea><button>Aprovar</button></form><form method="post" action="/admin/propostas/{{ proposal.id }}/devolver"><textarea name="details" placeholder="Ajustes necessários"></textarea><button>Devolver</button></form><form method="post" action="/admin/propostas/{{ proposal.id }}/rejeitar"><textarea name="details" placeholder="Motivo"></textarea><button>Rejeitar</button></form></section>{% endif %}</main></body></html>''',
'accounts.html': '''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/portal.css"><title>Contas</title></head><body>{% include '_portal_nav.html' %}<main><h1>Contas do sistema</h1><form class="form-card compact" method="post"><input name="name" placeholder="Nome" required><input name="email" type="email" placeholder="E-mail" required><input name="password" type="password" placeholder="Senha inicial" required><select name="role"><option value="GESTOR_DEPARTAMENTO">Gestor de departamento</option><option value="ANALISTA_TI">Analista T.I.</option><option value="ADMIN_TI">Admin T.I.</option></select><select name="department_id"><option value="">Sem departamento</option>{% for d in departments %}<option value="{{ d.id }}">{{ d.nome }}</option>{% endfor %}</select><button>Criar conta</button></form><div class="list">{% for account in users %}<div><b>{{ account.name }}</b><span>{{ account.email }} · {{ account.role }} · {{ account.department.nome if account.department else 'Todos os departamentos' }}</span></div>{% endfor %}</div></main></body></html>'''
}

CSS = '''*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#172033;font-family:Segoe UI,Arial,sans-serif}.portal-nav{display:flex;align-items:center;gap:26px;padding:14px 4vw;background:#12375f;color:#fff}.portal-nav a{color:#fff;text-decoration:none}.portal-nav>a{font-weight:800;font-size:19px}.portal-nav nav{display:flex;gap:16px;flex:1}.portal-nav button{background:#fff;color:#12375f;border:0;border-radius:6px;padding:7px 11px}main{width:min(1400px,94vw);margin:24px auto}.portal-hero{padding:22px;background:linear-gradient(120deg,#17365d,#2c6fa5);color:#fff;border-radius:12px}.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:16px}.metrics article,.form-card,.list,.cards a{background:#fff;border:1px solid #d7e0e8;border-radius:10px;padding:16px}.metrics span,.cards span,.cards small,.list span{display:block;color:#667085}.metrics strong{font-size:30px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.cards a{color:#172033;text-decoration:none}.chips{display:flex;gap:8px;flex-wrap:wrap}.chips span,.status,.permission{padding:4px 9px;border-radius:999px;background:#e7edf3}.title-row{display:flex;justify-content:space-between;align-items:center}.primary,button{display:inline-block;background:#1f4e78;color:#fff;border:0;border-radius:7px;padding:9px 13px;text-decoration:none}.list{display:flex;flex-direction:column;gap:8px}.list>a,.list>div{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;padding:10px;border-bottom:1px solid #e8edf1;color:#172033;text-decoration:none}.form-card{display:grid;gap:12px;max-width:850px}.form-card label{display:grid;gap:5px}.form-card input,.form-card select,.form-card textarea{padding:9px;border:1px solid #aebdca;border-radius:6px}.form-card textarea{min-height:80px}.form-card.compact{grid-template-columns:repeat(3,1fr);max-width:none}.warning,.error{padding:10px;border-left:4px solid #d97706;background:#fff8e7}.error{border-color:#dc2626;background:#fff1f0}.access-list{background:#fff;border:1px solid #d7e0e8;border-radius:8px;max-height:560px;overflow:auto;margin-bottom:14px}.access-list>div{display:grid;grid-template-columns:1fr auto;gap:10px;padding:8px;border-bottom:1px solid #edf0f2}.permission.permitido{background:#d9fbe3;color:#075b24}.permission.negado{background:#ffe0dd;color:#8a1712}.review{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.review form{display:grid;gap:7px}.review textarea{min-height:80px}.login-body{min-height:100vh;display:grid;place-items:center;background:#12375f}.login-card{width:min(420px,92vw);display:grid;gap:12px;padding:28px;background:#fff;border-radius:12px}.login-card label{display:grid;gap:5px}.login-card input{padding:10px;border:1px solid #aebdca;border-radius:6px}@media(max-width:850px){.portal-nav{align-items:flex-start;flex-direction:column}.portal-nav nav{flex-wrap:wrap}.cards,.metrics,.review,.form-card.compact{grid-template-columns:1fr}.list>a,.list>div{grid-template-columns:1fr}}'''

for name, content in TEMPLATES_MAP.items():
    (T / name).write_text(content, encoding='utf-8', newline='\n')
(S / 'portal.css').write_text(CSS, encoding='utf-8', newline='\n')

MAIN = APP / 'main.py'
main = MAIN.read_text(encoding='utf-8')
if 'from app.access_control import router as access_router' not in main:
    main += "\n\nfrom app.access_control import create_tables as create_access_tables, router as access_router\ncreate_access_tables()\napp.include_router(access_router)\n"
MAIN.write_text(main, encoding='utf-8', newline='\n')
py_compile.compile(str(APP / 'access_control.py'), doraise=True)
py_compile.compile(str(MAIN), doraise=True)

BOOTSTRAP = '''from getpass import getpass\nfrom sqlalchemy import select\nfrom sqlalchemy.orm import Session\nfrom app.database import engine\nfrom app.access_control import ROLE_ADMIN, SystemUser, create_tables, hash_password\n\ncreate_tables()\nemail = input("E-mail do admin T.I.: ").strip().lower()\nname = input("Nome: ").strip()\npassword = getpass("Senha inicial: ")\nif len(password) < 10:\n    raise SystemExit("Use uma senha com pelo menos 10 caracteres.")\nwith Session(engine) as session:\n    if session.scalar(select(SystemUser).where(SystemUser.email == email)):\n        raise SystemExit("Conta ja existe.")\n    session.add(SystemUser(name=name, email=email, password_hash=hash_password(password), role=ROLE_ADMIN, active=True))\n    session.commit()\nprint("Admin T.I. criado.")\n'''
(ROOT / 'criar_admin_ti.py').write_text(BOOTSTRAP, encoding='utf-8', newline='\n')
print('Modulo departamental, contas e propostas instalado.')
print('Crie o primeiro administrador com: python .\\criar_admin_ti.py')
