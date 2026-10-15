from __future__ import annotations



import traceback
import re
import json
from pathlib import Path
from app.models import FuncionarioDepartamento, SystemUserDepartamento, ImportacaoPlanilha, Cargo, SistemaCorporativo, CargoSistema, FuncionarioCargo, SystemUserCargo
import base64

import hashlib

import hmac

import os

import secrets

from datetime import datetime, timedelta, timezone

from typing import Annotated

from urllib.parse import urlparse



from fastapi import APIRouter, Depends, Form, HTTPException, Request, status, UploadFile, File
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

SESSION_IDLE_MINUTES = int(os.getenv('SESSION_IDLE_MINUTES', '10'))

MAX_CONCURRENT_SESSIONS = int(os.getenv('MAX_CONCURRENT_SESSIONS', '2'))

SESSION_ABSOLUTE_HOURS = int(os.getenv('SESSION_ABSOLUTE_HOURS', '10'))



PROPOSAL_STATUSES = {'RASCUNHO', 'EM_REVISAO', 'DEVOLVIDO', 'APROVADO', 'REJEITADO', 'PUBLICADO', 'ARQUIVADO'}

PROPOSAL_ORIGINS = {'CRIADO_VAZIO', 'COPIADO_DE_PERFIL', 'CONSOLIDADO_FUNCIONARIO', 'CONSOLIDADO_DEPARTAMENTO_COMUM', 'CONSOLIDADO_DEPARTAMENTO_UNIAO'}





class SystemUser(Base):

    __tablename__ = 'system_users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(160), nullable=False)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    username: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)

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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    user: Mapped[SystemUser] = relationship()





def create_tables():

    Base.metadata.create_all(bind=engine)





def safe_next_url(value: str | None) -> str:

    if not value:

        return '/portal'

    parsed = urlparse(value)

    if parsed.scheme or parsed.netloc or not value.startswith('/') or value.startswith('//'):

        return '/portal'

    return value





def normalize_username(value: str) -> str:

    username = value.strip().lower()

    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789._-')

    if not username or any(char not in allowed for char in username):

        raise HTTPException(400, 'Usuario invalido. Use letras, numeros, ponto, hifen ou sublinhado.')

    return username





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

    if not token:

        return None

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    login = session.scalar(

        select(LoginSession)

        .options(selectinload(LoginSession.user).selectinload(SystemUser.department))

        .where(LoginSession.token_hash == token_hash)

    )

    if not login:

        return None

    now = datetime.now(timezone.utc)

    idle_limit = now - timedelta(minutes=SESSION_IDLE_MINUTES)

    if login.expires_at <= now or login.last_activity_at <= idle_limit or not login.user.active:

        session.delete(login)

        session.commit()

        return None

    login.last_activity_at = now

    session.commit()

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









PUBLIC_PATHS = {'/login', '/health', '/session/activity'}

PROTECTED_PREFIXES = (

    '/portal', '/admin', '/estrutura', '/funcionarios', '/perfis', '/comparar', '/api', '/docs', '/redoc', '/openapi.json'

)





def _load_request_user(request: Request, session: Session):

    token = request.cookies.get('access_session')

    if not token:

        return None

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    login = session.scalar(

        select(LoginSession)

        .options(

            selectinload(LoginSession.user).selectinload(SystemUser.department)

        )

        .where(LoginSession.token_hash == token_hash)

    )

    if not login or login.expires_at <= datetime.now(timezone.utc) or not login.user.active:

        return None

    return login.user





async def integrated_access_middleware(request: Request, call_next):

    path = request.url.path

    if path.startswith('/static/'):

        return await call_next(request)



    with Session(engine) as session:

        user = _load_request_user(request, session)

        request.state.current_user = user



        protected = any(path == prefix or path.startswith(prefix + '/') for prefix in PROTECTED_PREFIXES)

        if protected and not user:

            return RedirectResponse(f'/login?next={request.url.path}', status_code=303)



        if user:

            if path.startswith('/funcionarios/'):

                try:

                    employee_id = int(path.rstrip('/').split('/')[-1])

                except ValueError:

                    employee_id = None

                if employee_id is not None:

                    employee = session.get(Funcionario, employee_id)

                    if not employee:

                        raise HTTPException(404, 'Funcionario nao encontrado')

                    enforce_department(user, employee.departamento_id)



            if path.startswith('/perfis/'):

                try:

                    profile_id = int(path.rstrip('/').split('/')[-1])

                except ValueError:

                    profile_id = None

                if profile_id is not None and user.role == ROLE_MANAGER:

                    allowed = session.scalar(

                        select(func.count())

                        .select_from(FuncionarioPerfil)

                        .join(Funcionario)

                        .where(

                            FuncionarioPerfil.perfil_id == profile_id,

                            Funcionario.departamento_id == user.department_id,

                        )

                    )

                    if not allowed:

                        raise HTTPException(403, 'Perfil fora do departamento')



            if path.startswith('/comparar') and user.role not in {ROLE_ADMIN, ROLE_ANALYST}:

                raise HTTPException(403, 'Comparacao restrita a T.I.')



    return await call_next(request)





@router.get('/login', response_class=HTMLResponse)

def login_page(request: Request, user: Annotated[SystemUser | None, Depends(current_user_optional)], next: str | None = None, reason: str | None = None):

    destination = safe_next_url(next)

    if user:

        return RedirectResponse(destination, status_code=303)

    message = 'Sua sessao expirou por inatividade. Entre novamente.' if reason == 'inactive' else None

    return templates.TemplateResponse(request=request, name='login.html', context={'error': message, 'next_url': destination})





@router.post('/login', response_class=HTMLResponse)

def login(request: Request, session: Db, login: Annotated[str, Form()], password: Annotated[str, Form()], next_url: Annotated[str, Form()] = '/portal'):

    identifier = login.strip().lower()

    user = session.scalar(

        select(SystemUser).where(

            (func.lower(SystemUser.email) == identifier)

            | (func.lower(SystemUser.username) == identifier)

        )

    )

    destination = safe_next_url(next_url)

    if not user or not user.active or not verify_password(password, user.password_hash):

        return templates.TemplateResponse(

            request=request,

            name='login.html',

            context={'error': 'E-mail, usuario ou senha invalidos', 'next_url': destination},

            status_code=401,

        )



    now = datetime.now(timezone.utc)

    # Remove sessões vencidas antes de aplicar o limite simultâneo.

    session.execute(

        delete(LoginSession).where(

            (LoginSession.user_id == user.id)

            & (

                (LoginSession.expires_at <= now)

                | (LoginSession.last_activity_at <= now - timedelta(minutes=SESSION_IDLE_MINUTES))

            )

        )

    )

    active_sessions = session.scalars(

        select(LoginSession)

        .where(LoginSession.user_id == user.id)

        .order_by(LoginSession.last_activity_at.asc(), LoginSession.id.asc())

    ).all()

    # Política escolhida: permite o novo acesso e encerra as sessões mais antigas.

    overflow = max(0, len(active_sessions) - MAX_CONCURRENT_SESSIONS + 1)

    for old_session in active_sessions[:overflow]:

        session.delete(old_session)



    raw = secrets.token_urlsafe(48)

    session.add(

        LoginSession(

            token_hash=hashlib.sha256(raw.encode()).hexdigest(),

            user_id=user.id,

            created_at=now,

            last_activity_at=now,

            expires_at=now + timedelta(hours=SESSION_ABSOLUTE_HOURS),

        )

    )

    session.commit()

    response = RedirectResponse(destination, status_code=303)

    response.set_cookie(

        'access_session',

        raw,

        httponly=True,

        samesite='lax',

        secure=False,

        max_age=SESSION_ABSOLUTE_HOURS * 3600,

    )

    return response







@router.post('/session/activity')

def session_activity(request: Request, session: Db):

    token = request.cookies.get('access_session')

    if not token:

        raise HTTPException(401, 'Sessao inexistente')

    login = session.scalar(select(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))

    if not login:

        raise HTTPException(401, 'Sessao inexistente')

    now = datetime.now(timezone.utc)

    if login.expires_at <= now or login.last_activity_at <= now - timedelta(minutes=SESSION_IDLE_MINUTES):

        session.delete(login)

        session.commit()

        raise HTTPException(401, 'Sessao expirada')

    login.last_activity_at = now

    session.commit()

    return {'ok': True}





@router.post('/logout')

def logout(request: Request, session: Db):

    token = request.cookies.get('access_session')

    if token:

        session.execute(delete(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))

        session.commit()

    response = RedirectResponse('/login', status_code=303)

    response.delete_cookie('access_session')

    return response









@router.get('/admin/contas/{account_id}/editar', response_class=HTMLResponse)

def account_edit_page(

    request: Request,

    account_id: int,

    session: Db,

    user: Annotated[SystemUser, Depends(require_admin)],

):

    account = session.get(SystemUser, account_id)

    if not account:

        raise HTTPException(404, 'Conta nao encontrada')

    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all()

    return templates.TemplateResponse(

        request=request,

        name='account_edit.html',

        context={

            'current_user': user,

            'user': user,

            'account': account,

            'departments': departments,

            'error': None,

        },

    )





@router.post('/admin/contas/{account_id}/editar', response_class=HTMLResponse)

def account_edit_save(

    request: Request,

    account_id: int,

    session: Db,

    user: Annotated[SystemUser, Depends(require_admin)],

    name: Annotated[str, Form()],

    username: Annotated[str, Form()],

    email: Annotated[str, Form()],

    role: Annotated[str, Form()],

    department_id: Annotated[int | None, Form()] = None,

    active: Annotated[str | None, Form()] = None,

    new_password: Annotated[str | None, Form()] = None,

):

    account = session.get(SystemUser, account_id)

    if not account:

        raise HTTPException(404, 'Conta nao encontrada')



    normalized_username = normalize_username(username)

    normalized_email = email.strip().lower()

    normalized_name = name.strip()

    valid_roles = {ROLE_ADMIN, ROLE_ANALYST, ROLE_MANAGER}



    error = None

    if not normalized_name or '@' not in normalized_email:

        error = 'Nome ou e-mail invalido.'

    elif role not in valid_roles:

        error = 'Papel invalido.'

    elif role == ROLE_MANAGER and not department_id:

        error = 'Gestor de departamento precisa ter um departamento.'

    elif session.scalar(select(SystemUser).where(func.lower(SystemUser.username) == normalized_username, SystemUser.id != account.id)):

        error = 'Este nome de usuario ja esta em uso.'

    elif session.scalar(select(SystemUser).where(func.lower(SystemUser.email) == normalized_email, SystemUser.id != account.id)):

        error = 'Este e-mail ja esta em uso.'

    elif department_id and not session.get(Departamento, department_id):

        error = 'Departamento invalido.'

    elif new_password and len(new_password) < 6:

        error = 'A nova senha precisa ter pelo menos 6 caracteres.'



    if error:

        departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all()

        return templates.TemplateResponse(

            request=request,

            name='account_edit.html',

            context={

                'current_user': user,

                'user': user,

                'account': account,

                'departments': departments,

                'error': error,

            },

            status_code=400,

        )



    account.name = normalized_name

    account.username = normalized_username

    account.email = normalized_email

    account.role = role

    account.department_id = department_id if role == ROLE_MANAGER else department_id

    account.active = active == 'on'

    if new_password:

        account.password_hash = hash_password(new_password)

    session.commit()

    return RedirectResponse('/admin/contas', status_code=303)





@router.get('/portal', response_class=HTMLResponse)

def portal(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)]):

    employee_count = session.scalar(select(func.count()).select_from(Funcionario).where(Funcionario.departamento_id == user.department_id)) if user.role == ROLE_MANAGER else session.scalar(select(func.count()).select_from(Funcionario))

    proposal_query = select(func.count()).select_from(ProfileProposal).where(

        ProfileProposal.workflow_status == 'EM_REVISAO'

    )

    if user.role == ROLE_MANAGER: proposal_query = proposal_query.where(ProfileProposal.department_id == user.department_id)

    return templates.TemplateResponse(request=request, name='portal.html', context={'user': user, 'employee_count': employee_count or 0, 'proposal_count': session.scalar(proposal_query) or 0})





@router.get('/portal/funcionarios', response_class=HTMLResponse)
def portal_employees(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
    nome: str = '',
    departamento_id: int | None = None,
    cargo_id: int | None = None,
    situacao: str = 'TODOS',
):
    nome=nome.strip(); ti_manager=user.role in {ROLE_ADMIN,ROLE_ANALYST}
    query=scoped_employee_query(user)
    if nome:
        term=f'%{nome}%'; query=query.where((Funcionario.nome.ilike(term)) | (Funcionario.login.ilike(term)))
    if ti_manager and departamento_id: query=query.where(Funcionario.departamento_id==departamento_id)
    if cargo_id: query=query.join(FuncionarioCargo,FuncionarioCargo.funcionario_id==Funcionario.id).where(FuncionarioCargo.cargo_id==cargo_id)
    if situacao=='ATIVO': query=query.where(Funcionario.ativo.is_(True))
    elif situacao=='INATIVO': query=query.where(Funcionario.ativo.is_(False))
    employees=session.scalars(query).unique().all()
    employee_rows=[]
    for employee in employees:
        cargos=session.scalars(select(Cargo.nome).join(FuncionarioCargo,FuncionarioCargo.cargo_id==Cargo.id).where(FuncionarioCargo.funcionario_id==employee.id).order_by(Cargo.nome)).all()
        employee_rows.append({'employee':employee,'cargos':list(cargos)})
    departments=session.scalars(select(Departamento).order_by(Departamento.nome)).all() if ti_manager else []
    cargo_query=select(Cargo).where(Cargo.ativo.is_(True)).order_by(Cargo.nome)
    selected_department=departamento_id if ti_manager else user.department_id
    if selected_department: cargo_query=cargo_query.where(Cargo.departamento_id==selected_department)
    cargos=session.scalars(cargo_query).all()
    return templates.TemplateResponse(request=request,name='portal_employees.html',context={'user':user,'employee_rows':employee_rows,'employees':employees,'departments':departments,'cargos':cargos,'filter_name':nome,'filter_department_id':departamento_id,'filter_cargo_id':cargo_id,'filter_status':situacao,'show_department_filter':ti_manager})

@router.get('/portal/funcionarios/{employee_id}', response_class=HTMLResponse)

def portal_employee_detail(request: Request, employee_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):

    employee = session.scalar(select(Funcionario).options(selectinload(Funcionario.departamento), selectinload(Funcionario.perfis).selectinload(FuncionarioPerfil.perfil)).where(Funcionario.id == employee_id))

    if not employee: raise HTTPException(404, 'Funcionario nao encontrado')

    enforce_department(user, employee.departamento_id)

    return templates.TemplateResponse(request=request, name='portal_employee.html', context={'user': user, 'employee': employee})









@router.get('/portal/funcionarios/{employee_id}/editar', response_class=HTMLResponse)

def portal_employee_edit(request: Request, employee_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):

    employee = session.scalar(select(Funcionario).options(selectinload(Funcionario.departamento)).where(Funcionario.id == employee_id))

    if not employee:

        raise HTTPException(404, 'Funcionario nao encontrado')

    enforce_department(user, employee.departamento_id)

    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if user.role in {ROLE_ADMIN, ROLE_ANALYST} else [employee.departamento]

    return templates.TemplateResponse(request=request, name='portal_employee_edit.html', context={'user': user, 'employee': employee, 'departments': departments, 'error': None})





@router.post('/portal/funcionarios/{employee_id}/editar', response_class=HTMLResponse)

def portal_employee_update(request: Request, employee_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)], name: Annotated[str, Form()], login: Annotated[str, Form()], department_id: Annotated[int, Form()], active: Annotated[str | None, Form()] = None):

    employee = session.scalar(select(Funcionario).options(selectinload(Funcionario.departamento)).where(Funcionario.id == employee_id))

    if not employee:

        raise HTTPException(404, 'Funcionario nao encontrado')

    enforce_department(user, employee.departamento_id)

    if user.role == ROLE_MANAGER:

        department_id = user.department_id

    elif not session.get(Departamento, department_id):

        raise HTTPException(400, 'Departamento invalido')

    normalized_name = name.strip()

    normalized_login = login.strip().lower()

    if not normalized_name or not normalized_login or any(char.isspace() for char in normalized_login):

        raise HTTPException(400, 'Nome ou login invalido')

    duplicate = session.scalar(select(Funcionario).where(func.lower(Funcionario.login) == normalized_login, Funcionario.id != employee.id))

    if duplicate:

        departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if user.role in {ROLE_ADMIN, ROLE_ANALYST} else [employee.departamento]

        return templates.TemplateResponse(request=request, name='portal_employee_edit.html', context={'user': user, 'employee': employee, 'departments': departments, 'error': 'Ja existe outro funcionario com este login.'}, status_code=409)

    employee.nome = normalized_name

    employee.login = normalized_login

    employee.departamento_id = department_id

    employee.ativo = active == 'on'

    session.commit()

    return RedirectResponse(f'/funcionarios/{employee.id}', status_code=303)





@router.get('/portal/propostas', response_class=HTMLResponse)

def proposals(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)]):

    # VISIBILIDADE_PROPOSTAS_POR_FLUXO_V1

    # EM_REVISAO e a fila pendente dos departamentos. Rascunhos, devolvidas e

    # rejeitadas continuam visiveis somente ao autor para que possam ser enviadas.

    author_work_statuses = {'RASCUNHO', 'DEVOLVIDO', 'REJEITADO'}



    if user.role == ROLE_MANAGER:

        query = (

            select(ProfileProposal)

            .options(selectinload(ProfileProposal.department))

            .where(ProfileProposal.department_id == user.department_id)

            .where(

                (ProfileProposal.workflow_status == 'EM_REVISAO')

                | (

                    (ProfileProposal.created_by_id == user.id)

                    & (ProfileProposal.workflow_status.in_(author_work_statuses))

                )

            )

            .order_by(ProfileProposal.created_at.desc())

        )

    else:

        query = (

            select(ProfileProposal)

            .options(selectinload(ProfileProposal.department))

            .where(

                (ProfileProposal.workflow_status == 'EM_REVISAO')

                | (

                    (ProfileProposal.created_by_id == user.id)

                    & (ProfileProposal.workflow_status.in_(author_work_statuses))

                )

            )

            .order_by(ProfileProposal.created_at.desc())

        )



    proposals_list = session.scalars(query).unique().all()

    return templates.TemplateResponse(

        request=request,

        name='proposals.html',

        context={'user': user, 'proposals': proposals_list},

    )





@router.get('/portal/propostas/nova', response_class=HTMLResponse)

def proposal_new(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)]):

    employees = session.scalars(scoped_employee_query(user)).all()

    profile_query = select(Perfil).order_by(Perfil.nome)

    if user.role == ROLE_MANAGER: profile_query = profile_query.where(Perfil.id.in_(profile_ids_for_department(session, user.department_id)))

    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if user.role in {ROLE_ADMIN, ROLE_ANALYST} else [user.department]

    accesses = session.scalars(select(Acesso).order_by(Acesso.caminho_completo, Acesso.tela_final, Acesso.botao)).all()

    return templates.TemplateResponse(request=request, name='proposal_new.html', context={'user': user, 'employees': employees, 'profiles': session.scalars(profile_query).all(), 'departments': departments, 'accesses': accesses})





@router.post('/portal/propostas/nova')

def proposal_create(session: Db, user: Annotated[SystemUser, Depends(require_user)], name: Annotated[str, Form()], origin: Annotated[str, Form()], department_id: Annotated[int, Form()], description: Annotated[str, Form()] = '', justification: Annotated[str, Form()] = '', source_profile_id: Annotated[str, Form()] = '', source_employee_id: Annotated[str, Form()] = '', access_selection_present: Annotated[str, Form()] = '', access_ids: Annotated[list[int] | None, Form()] = None):

    # OPTIONAL_FORM_IDS_FIXED: selects HTML enviam string vazia quando nenhuma base é escolhida.

    try:

        source_profile_id = int(source_profile_id) if source_profile_id.strip() else None

        source_employee_id = int(source_employee_id) if source_employee_id.strip() else None

    except ValueError:

        raise HTTPException(status_code=400, detail='Perfil ou funcionário base inválido')



    if origin not in {'CRIADO_DO_ZERO', 'COPIADO_DE_PERFIL', 'CONSOLIDADO_FUNCIONARIO'}: raise HTTPException(400, 'Selecione Criar do zero, Copiar perfil ou Consolidado de funcionario')

    if origin == 'COPIADO_DE_PERFIL' and not source_profile_id:

        raise HTTPException(400, 'Selecione o perfil que deseja copiar')

    if origin == 'CONSOLIDADO_FUNCIONARIO' and not source_employee_id:

        raise HTTPException(400, 'Selecione o funcionario que deseja consolidar')

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

    # PROPOSTA_DO_ZERO_V3: CRIADO_DO_ZERO usa o mapa vazio e aplica os access_ids selecionados.

    access_map = {}

    if origin == 'COPIADO_DE_PERFIL' and source_profile_id: access_map = proposal_access_map_from_profile(session, source_profile_id)

    elif origin == 'CONSOLIDADO_FUNCIONARIO' and source_employee_id: access_map = proposal_access_map_from_employee(session, source_employee_id)

    elif origin in {'CONSOLIDADO_DEPARTAMENTO_COMUM', 'CONSOLIDADO_DEPARTAMENTO_UNIAO'}: access_map = proposal_access_map_from_department(session, department_id, origin)

    if access_selection_present == '1': access_map = {access_id: 'Permitido' for access_id in set(access_ids or [])}

    for access_id, access_status in access_map.items(): session.add(ProfileProposalAccess(proposal_id=proposal.id, access_id=access_id, status=access_status))

    create_history(session, proposal.id, user.id, 'CRIADA', f'Origem: {origin}')

    session.commit()

    return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)





@router.get('/portal/propostas/base-acessos')

def proposal_base_accesses(

    origin: str,

    session: Db,

    user: Annotated[SystemUser, Depends(require_user)],

    source_id: int,

):

    if origin == 'COPIADO_DE_PERFIL':

        if user.role == ROLE_MANAGER:

            allowed = session.scalar(select(func.count()).select_from(FuncionarioPerfil).join(Funcionario).where(FuncionarioPerfil.perfil_id == source_id, Funcionario.departamento_id == user.department_id))

            if not allowed: raise HTTPException(403, 'Perfil fora do departamento')

        access_map = proposal_access_map_from_profile(session, source_id)

    elif origin == 'CONSOLIDADO_FUNCIONARIO':

        employee = session.get(Funcionario, source_id)

        if not employee: raise HTTPException(404, 'Funcionario nao encontrado')

        enforce_department(user, employee.departamento_id)

        access_map = proposal_access_map_from_employee(session, source_id)

    else:

        raise HTTPException(400, 'Origem invalida')

    return {'access_ids': [int(access_id) for access_id, status in access_map.items() if str(status).casefold() == 'permitido']}





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

    # Se o navegador repetir o envio depois de colocar a proposta em revisao,

    # apenas retorna para os detalhes sem gerar erro ou duplicar o historico.

    if proposal.workflow_status == 'EM_REVISAO':

        return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)

    if proposal.workflow_status not in {'RASCUNHO', 'DEVOLVIDO', 'REJEITADO'}:

        raise HTTPException(409, f'A proposta nao pode ser enviada no estado {proposal.workflow_status}')

    proposal.workflow_status = 'EM_REVISAO'; proposal.submitted_at = datetime.now(timezone.utc)

    create_history(session, proposal.id, user.id, 'ENVIADA_PARA_TI')

    session.commit(); return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)





@router.get('/portal/perfis', response_class=HTMLResponse)

def portal_profiles(

    request: Request,

    session: Db,

    user: Annotated[SystemUser, Depends(require_user)],

    nome: str = '',

    departamento_id: str = '',

    origem: str = '',

    situacao: str = 'ATIVO',

):

    nome = nome.strip()

    origem = origem.strip().upper()

    department_id_value = int(departamento_id) if departamento_id.strip().isdigit() else None

    situacao = situacao.strip().upper()

    show_department_filter = user.role in {ROLE_ADMIN, ROLE_ANALYST}

    generated_ids_query = select(ProfileProposal.imported_result_profile_id).where(

        ProfileProposal.imported_result_profile_id.is_not(None)

    )

    generated_profile_ids = set(session.scalars(generated_ids_query).all())

    query = select(Perfil).options(selectinload(Perfil.departamento)).order_by(Perfil.nome)

    if user.role == ROLE_MANAGER:

        query = query.where(Perfil.id.in_(profile_ids_for_department(session, user.department_id)))

    elif department_id_value:

        query = query.where(Perfil.departamento_id == department_id_value)

    if nome:

        query = query.where(Perfil.nome.ilike(f'%{nome}%'))

    if situacao == 'INATIVO':

        query = query.where(func.upper(Perfil.situacao) == 'INATIVO')

    elif situacao == 'TODOS':

        pass

    else:

        query = query.where(func.upper(Perfil.situacao).in_({'ATIVO', 'COMPLETO', 'PENDENTE'}))

    if origem == 'PROPOSTA':

        query = query.where(Perfil.id.in_(generated_profile_ids or {-1}))

    elif origem == 'ERP':

        query = query.where(Perfil.id.not_in(generated_profile_ids or {-1}))

    profiles = session.scalars(query).unique().all()

    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if show_department_filter else []

    return templates.TemplateResponse(

        request=request,

        name='portal_profiles.html',

        context={

            'user': user,

            'profiles': profiles,

            'departments': departments,

            'filter_name': nome,

            'filter_department_id': department_id_value,

            'filter_origin': origem,

            'filter_status': situacao,

            'show_department_filter': show_department_filter,

            'generated_profile_ids': generated_profile_ids,

        },

    )





@router.get('/portal/perfis/{profile_id}', response_class=HTMLResponse)

def portal_profile_detail(

    request: Request,

    profile_id: int,

    session: Db,

    user: Annotated[SystemUser, Depends(require_user)],

):

    profile = session.scalar(

        select(Perfil)

        .options(

            selectinload(Perfil.departamento),

            selectinload(Perfil.acessos).selectinload(PerfilAcesso.acesso),

        )

        .where(Perfil.id == profile_id)

    )

    if not profile:

        raise HTTPException(404, 'Perfil nao encontrado')

    if user.role == ROLE_MANAGER and profile.id not in set(session.scalars(profile_ids_for_department(session, user.department_id)).all()):

        raise HTTPException(403, 'Perfil fora do departamento')

    proposal = session.scalar(

        select(ProfileProposal)

        .where(ProfileProposal.imported_result_profile_id == profile_id)

        .order_by(ProfileProposal.id.desc())

    )

    accesses = sorted(

        profile.acessos,

        key=lambda item: (

            item.acesso.caminho_completo.casefold(),

            item.acesso.tela_final.casefold(),

            item.acesso.botao.casefold(),

        ),

    )

    return templates.TemplateResponse(

        request=request,

        name='portal_profile.html',

        context={

            'user': user,

            'profile': profile,

            'accesses': accesses,

            'generated_proposal': proposal,

            'is_admin': user.role == ROLE_ADMIN,

        },

    )





@router.get('/admin/contas', response_class=HTMLResponse)

def accounts(

    request: Request,

    session: Db,

    user: Annotated[SystemUser, Depends(require_admin)],

):

    accounts = session.scalars(

        select(SystemUser)

        .options(selectinload(SystemUser.department))

        .order_by(SystemUser.name, SystemUser.email)

    ).all()

    departments = session.scalars(

        select(Departamento).order_by(Departamento.nome)

    ).all()

    return templates.TemplateResponse(

        request=request,

        name='accounts.html',

        context={

            'current_user': user,

            'user': user,

            'accounts': accounts,

            'users': accounts,

            'system_users': accounts,

            'departments': departments,

            'error': None,

        },

    )



@router.post('/admin/contas')

def account_create(session: Db, user: Annotated[SystemUser, Depends(require_admin)], name: Annotated[str, Form()], username: Annotated[str, Form()], email: Annotated[str, Form()], password: Annotated[str, Form()], role: Annotated[str, Form()], department_id: Annotated[int | None, Form()] = None):

    if len(password) < 6: raise HTTPException(400, 'A senha precisa ter pelo menos 6 caracteres')

    if role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_ANALYST}: raise HTTPException(400, 'Papel invalido')

    if role == ROLE_MANAGER and not department_id: raise HTTPException(400, 'Gestor precisa de departamento')

    session.add(SystemUser(name=name.strip(), username=normalize_username(username), email=email.strip().lower(), password_hash=hash_password(password), role=role, department_id=department_id, active=True))

    session.commit(); return RedirectResponse('/admin/contas', status_code=303)





@router.post('/admin/propostas/{proposal_id}/{action}')

def proposal_review(proposal_id: int, action: str, session: Db, user: Annotated[SystemUser, Depends(require_admin)], details: Annotated[str, Form()] = ''):

    proposal = session.get(ProfileProposal, proposal_id)

    if not proposal: raise HTTPException(404, 'Proposta nao encontrada')

    mapping = {'aprovar': 'APROVADO', 'rejeitar': 'REJEITADO', 'devolver': 'DEVOLVIDO'}

    if action not in mapping: raise HTTPException(400, 'Acao invalida')

    proposal.workflow_status = mapping[action]; proposal.reviewed_by_id = user.id; proposal.reviewed_at = datetime.now(timezone.utc)

    if action == 'aprovar':

        proposal = session.scalar(select(ProfileProposal).options(selectinload(ProfileProposal.accesses)).where(ProfileProposal.id == proposal_id))

        if proposal.imported_result_profile_id is None:

            existing = session.scalar(select(Perfil).where(func.lower(Perfil.nome) == proposal.name.strip().lower()))

            if existing:

                raise HTTPException(409, 'Ja existe um perfil com este nome')

            generated = Perfil(nome=proposal.name.strip(), situacao='Ativo', departamento_id=proposal.department_id, ultima_atualizacao=datetime.now(timezone.utc))

            session.add(generated)

            session.flush()

            for pa in proposal.accesses:

                session.add(PerfilAcesso(perfil_id=generated.id, acesso_id=pa.access_id, status=pa.status or 'Permitido'))

            proposal.imported_result_profile_id = generated.id

        details = ((details.strip() + ' | ') if details.strip() else '') + 'Perfil gerado na proposta'



    create_history(session, proposal.id, user.id, mapping[action], details.strip() or None)

    session.commit(); return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)





# PROPOSAL_UI_V3 - integração corrigida, sem alterar login ou sessão

def proposal_for_user(session: Session, user: SystemUser, proposal_id: int):

    proposal=session.scalar(select(ProfileProposal).options(selectinload(ProfileProposal.department),selectinload(ProfileProposal.accesses).selectinload(ProfileProposalAccess.access)).where(ProfileProposal.id==proposal_id))

    if not proposal: raise HTTPException(404,'Proposta nao encontrada')

    enforce_department(user,proposal.department_id)

    return proposal



def proposal_can_edit(user: SystemUser, proposal: ProfileProposal):

    return proposal.created_by_id==user.id and proposal.workflow_status in {'RASCUNHO','DEVOLVIDO','REJEITADO'}



def proposal_can_delete(user: SystemUser, proposal: ProfileProposal):

    return proposal.created_by_id==user.id or user.role in {ROLE_ADMIN,ROLE_ANALYST}



@router.get('/portal/propostas/{proposal_id}/editar',response_class=HTMLResponse)

def proposal_edit_v3(request:Request,proposal_id:int,session:Db,user:Annotated[SystemUser,Depends(require_user)]):

    proposal=proposal_for_user(session,user,proposal_id)

    if not proposal_can_edit(user,proposal): raise HTTPException(403,'A proposta nao pode ser editada neste status')

    accesses=session.scalars(select(Acesso).order_by(Acesso.caminho_completo,Acesso.tela_final,Acesso.botao)).all()

    selected={item.access_id for item in proposal.accesses}

    return templates.TemplateResponse(request=request,name='proposal_edit.html',context={'user':user,'proposal':proposal,'accesses':accesses,'selected':selected})



@router.post('/portal/propostas/{proposal_id}/editar')

def proposal_update_v3(proposal_id:int,session:Db,user:Annotated[SystemUser,Depends(require_user)],name:Annotated[str,Form()],description:Annotated[str,Form()]='',justification:Annotated[str,Form()]='',access_ids:Annotated[list[int]|None,Form()]=None):

    proposal=proposal_for_user(session,user,proposal_id)

    if not proposal_can_edit(user,proposal): raise HTTPException(403,'A proposta nao pode ser editada neste status')

    proposal.name=name.strip(); proposal.description=description.strip() or None; proposal.justification=justification.strip() or None

    ids=set(access_ids or [])

    valid=set(session.scalars(select(Acesso.id).where(Acesso.id.in_(ids or {-1}))).all())

    proposal.accesses.clear(); session.flush()

    proposal.accesses.extend(ProfileProposalAccess(access_id=i,status='Permitido') for i in valid)

    create_history(session,proposal.id,user.id,'PROPOSTA_EDITADA',f'{len(valid)} acessos selecionados')

    session.commit(); return RedirectResponse(f'/portal/propostas/{proposal.id}',status_code=303)



@router.post('/portal/propostas/{proposal_id}/excluir')

def proposal_delete_v3(proposal_id:int,session:Db,user:Annotated[SystemUser,Depends(require_user)],reason:Annotated[str,Form()]=''):

    proposal=proposal_for_user(session,user,proposal_id)

    if not proposal_can_delete(user,proposal): raise HTTPException(403,'Sem permissao para excluir esta proposta')

    if len(reason.strip())<3: raise HTTPException(400,'Informe o motivo da exclusao')

    session.delete(proposal); session.commit()

    return RedirectResponse('/portal/propostas',status_code=303)



@router.post('/portal/perfis/{profile_id}/situacao')

def portal_profile_status(

    profile_id: int,

    session: Db,

    user: Annotated[SystemUser, Depends(require_admin)],

    situacao: Annotated[str, Form()],

):

    profile = session.get(Perfil, profile_id)

    if not profile:

        raise HTTPException(404, 'Perfil nao encontrado')

    generated = session.scalar(

        select(func.count()).select_from(ProfileProposal).where(

            ProfileProposal.imported_result_profile_id == profile_id

        )

    )

    if not generated:

        raise HTTPException(409, 'Somente perfis gerados em propostas podem ser inativados por esta acao')

    if situacao not in {'Ativo', 'Inativo'}:

        raise HTTPException(400, 'Situacao invalida')

    profile.situacao = situacao

    profile.ultima_atualizacao = datetime.now(timezone.utc)

    session.commit()

    return RedirectResponse(f'/portal/perfis/{profile.id}', status_code=303)



# API_ORIGEM_PERFIL_PROPOSTA_CLASSICA_V2

@router.get('/api/perfis/{profile_id}/origem-proposta')

def classic_profile_proposal_origin(

    profile_id: int,

    session: Db,

    user: Annotated[SystemUser, Depends(require_user)],

):

    generated = session.scalar(

        select(func.count()).select_from(ProfileProposal).where(

            ProfileProposal.imported_result_profile_id == profile_id

        )

    )

    return {'generated': bool(generated), 'can_manage': user.role == ROLE_ADMIN}


def sync_system_user_departments(session: Session, account_id: int, department_ids: list[int]):
    valid = set(session.scalars(select(Departamento.id).where(Departamento.id.in_(set(department_ids or [-1])))).all())
    session.query(SystemUserDepartamento).filter(SystemUserDepartamento.system_user_id == account_id).delete()
    session.add_all(SystemUserDepartamento(system_user_id=account_id, departamento_id=value) for value in valid)
    return sorted(valid)


def sync_employee_departments(session: Session, employee_id: int, department_ids: list[int]):
    valid = set(session.scalars(select(Departamento.id).where(Departamento.id.in_(set(department_ids or [-1])))).all())
    session.query(FuncionarioDepartamento).filter(FuncionarioDepartamento.funcionario_id == employee_id).delete()
    session.add_all(FuncionarioDepartamento(funcionario_id=employee_id, departamento_id=value) for value in valid)
    return sorted(valid)


def employee_department_names(session: Session, employee_id: int):
    return session.scalars(select(Departamento.nome).join(FuncionarioDepartamento, FuncionarioDepartamento.departamento_id == Departamento.id).where(FuncionarioDepartamento.funcionario_id == employee_id).order_by(Departamento.nome)).all()

# IMPORTACAO_E_DEPARTAMENTOS_NN_V1
IMPORT_TEMP_DIR = Path(__file__).resolve().parent.parent / 'data' / 'importacoes_temp'
IMPORT_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def require_admin_ti_only(user: Annotated[SystemUser, Depends(require_user)]):
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail='Funcionalidade exclusiva do Administrador de T.I.')
    return user

@router.get('/portal/importacoes', response_class=HTMLResponse)
def importacoes_page(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_admin_ti_only)]):
    history = session.scalars(select(ImportacaoPlanilha).order_by(ImportacaoPlanilha.criado_em.desc()).limit(20)).all()
    return templates.TemplateResponse(request=request, name='importacoes.html', context={'user': user, 'history': history, 'preview': None})


@router.post('/portal/importacoes/preview', response_class=HTMLResponse)
async def importacoes_preview(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin_ti_only)],
    arquivo_consulta: UploadFile = File(...),
    arquivo_mapa: UploadFile = File(...),
):
    files = (arquivo_consulta, arquivo_mapa)
    if any(not item.filename or not item.filename.lower().endswith('.xlsx') for item in files):
        raise HTTPException(400, 'Envie os dois arquivos em formato .xlsx')
    consulta_data, mapa_data = await arquivo_consulta.read(), await arquivo_mapa.read()
    if len(consulta_data) > 80 * 1024 * 1024 or len(mapa_data) > 80 * 1024 * 1024:
        raise HTTPException(413, 'Cada arquivo deve ter no maximo 80 MB')
    from app.importacao_planilhas import preview_files
    report = preview_files(consulta_data, mapa_data)
    token = hashlib.sha256(consulta_data + b'|DUAL|' + mapa_data).hexdigest()
    (IMPORT_TEMP_DIR / f'{token}_consulta.xlsx').write_bytes(consulta_data)
    (IMPORT_TEMP_DIR / f'{token}_mapa.xlsx').write_bytes(mapa_data)
    (IMPORT_TEMP_DIR / f'{token}.json').write_text(json.dumps({
        'consulta_filename': arquivo_consulta.filename,
        'mapa_filename': arquivo_mapa.filename,
    }, ensure_ascii=False), encoding='utf-8')
    history = session.scalars(select(ImportacaoPlanilha).order_by(ImportacaoPlanilha.criado_em.desc()).limit(20)).all()
    return templates.TemplateResponse(request=request, name='importacoes.html', context={'user': user, 'history': history, 'preview': report, 'token': token})


@router.post('/portal/importacoes/confirmar', response_class=HTMLResponse)
def importacoes_confirmar(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin_ti_only)],
    token: Annotated[str, Form()],
):
    paths = []
    filenames = ['Consulta_Acessos.xlsx', 'Mapa_Geral_Acessos.xlsx']
    try:
        if not re.fullmatch(r'[a-f0-9]{64}', token):
            raise ValueError('Token de importacao invalido.')
        consulta_path = IMPORT_TEMP_DIR / f'{token}_consulta.xlsx'
        mapa_path = IMPORT_TEMP_DIR / f'{token}_mapa.xlsx'
        meta_path = IMPORT_TEMP_DIR / f'{token}.json'
        paths = [consulta_path, mapa_path, meta_path]
        if not all(path.exists() for path in paths):
            raise ValueError('A pre-visualizacao expirou. Envie as duas planilhas novamente.')
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        filenames = [meta.get('consulta_filename') or filenames[0], meta.get('mapa_filename') or filenames[1]]
        # REIMPORTACAO_PERMITIDA_V1
        execution_hash = hashlib.sha256(
            f"{token}:{datetime.now(timezone.utc).isoformat()}:{secrets.token_hex(8)}".encode()
        ).hexdigest()
        job = ImportacaoPlanilha(
            arquivo=' + '.join(filenames),
            hash_arquivo=execution_hash,
            tipo='XLSX_DUPLO',
            status='PROCESSANDO',
            criado_por_id=user.id,
        )
        session.add(job)
        session.flush()
        from app.importacao_planilhas import import_workbooks
        result = import_workbooks(
            session,
            consulta_path.read_bytes(),
            mapa_path.read_bytes(),
            filenames[0],
            filenames[1],
        )
        result['hash_conjunto_importado'] = token
        result['reimportacao'] = True
        job.status = 'CONCLUIDA'
        job.resultado_json = json.dumps(result, ensure_ascii=False)
        session.commit()
        for path in paths:
            path.unlink(missing_ok=True)
        return RedirectResponse('/portal/importacoes?status=sucesso', status_code=303)
    except Exception as exc:
        session.rollback()
        error_text = f'{type(exc).__name__}: {exc}'
        print('[ERRO IMPORTACAO]', error_text)
        traceback.print_exc()
        try:
            session.add(ImportacaoPlanilha(
                arquivo=' + '.join(filenames),
                hash_arquivo=token if re.fullmatch(r'[a-f0-9]{64}', token or '') else '0' * 64,
                tipo='XLSX_DUPLO', status='ERRO',
                resultado_json=json.dumps({'erro': error_text}, ensure_ascii=False),
                criado_por_id=user.id,
            ))
            session.commit()
        except Exception:
            session.rollback()
        history = session.scalars(select(ImportacaoPlanilha).order_by(ImportacaoPlanilha.criado_em.desc()).limit(20)).all()
        return templates.TemplateResponse(request=request, name='importacoes.html', context={'user': user, 'history': history, 'preview': None, 'import_error': error_text}, status_code=400)


# MODULO_CADASTROS_ORGANIZACIONAIS_V1
@router.get('/admin/cadastros', response_class=HTMLResponse)
def cadastros_home(request: Request, user: Annotated[SystemUser, Depends(require_admin)]):
    return templates.TemplateResponse(request=request, name='cadastros.html', context={'user': user})

@router.get('/admin/departamentos', response_class=HTMLResponse)
def cadastros_departamentos(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_admin)]):
    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all()
    return templates.TemplateResponse(request=request, name='departments.html', context={'user': user, 'departments': departments})

@router.post('/admin/departamentos')
def cadastros_departamento_criar(session: Db, user: Annotated[SystemUser, Depends(require_admin)], nome: Annotated[str, Form()]):
    value=nome.strip()
    if not value: raise HTTPException(400,'Informe o nome do departamento')
    if session.scalar(select(Departamento).where(func.lower(Departamento.nome)==value.lower())): raise HTTPException(409,'Departamento ja cadastrado')
    session.add(Departamento(nome=value,ativo=True)); session.commit()
    return RedirectResponse('/admin/departamentos',status_code=303)

@router.get('/admin/departamentos/{department_id}', response_class=HTMLResponse)
def cadastros_departamento_detalhe(request: Request, department_id: int, session: Db, user: Annotated[SystemUser, Depends(require_admin)]):
    department=session.get(Departamento,department_id)
    if not department: raise HTTPException(404,'Departamento nao encontrado')
    cargos=session.scalars(select(Cargo).where(Cargo.departamento_id==department_id).order_by(Cargo.nome)).all()
    cargo_ids=[item.id for item in cargos]
    systems_by_cargo={item.id: [] for item in cargos}; users_by_cargo={item.id: [] for item in cargos}
    if cargo_ids:
        for cargo_id,sistema in session.execute(select(CargoSistema.cargo_id,SistemaCorporativo).join(SistemaCorporativo,SistemaCorporativo.id==CargoSistema.sistema_id).where(CargoSistema.cargo_id.in_(cargo_ids)).order_by(SistemaCorporativo.nome)):
            systems_by_cargo[cargo_id].append(sistema)
        for cargo_id,employee in session.execute(select(FuncionarioCargo.cargo_id,Funcionario).join(Funcionario,Funcionario.id==FuncionarioCargo.funcionario_id).where(FuncionarioCargo.cargo_id.in_(cargo_ids)).order_by(Funcionario.nome)):
            users_by_cargo[cargo_id].append(employee)
    employees=session.scalars(select(Funcionario).where(Funcionario.departamento_id==department_id).order_by(Funcionario.nome)).all()
    systems=session.scalars(select(SistemaCorporativo).where(SistemaCorporativo.ativo.is_(True)).order_by(SistemaCorporativo.nome)).all()
    return templates.TemplateResponse(request=request,name='department_detail.html',context={'user':user,'department':department,'cargos':cargos,'systems_by_cargo':systems_by_cargo,'users_by_cargo':users_by_cargo,'employees':employees,'systems':systems})

@router.post('/admin/departamentos/{department_id}/cargos')
def cadastros_cargo_criar(department_id:int,session:Db,user:Annotated[SystemUser,Depends(require_admin)],nome:Annotated[str,Form()],descricao:Annotated[str,Form()]='',observacao:Annotated[str,Form()]=''):
    department=session.get(Departamento,department_id)
    if not department: raise HTTPException(404,'Departamento nao encontrado')
    value=nome.strip()
    if not value: raise HTTPException(400,'Informe o nome do cargo')
    if session.scalar(select(Cargo).where(Cargo.departamento_id==department_id,func.lower(Cargo.nome)==value.lower())): raise HTTPException(409,'Cargo ja cadastrado neste departamento')
    session.add(Cargo(departamento_id=department_id,nome=value,descricao=descricao.strip() or None,observacao=observacao.strip() or None,ativo=True)); session.commit()
    return RedirectResponse(f'/admin/departamentos/{department_id}',status_code=303)

@router.post('/admin/cargos/{cargo_id}/vinculos')
def cadastros_cargo_vinculos(cargo_id:int,session:Db,user:Annotated[SystemUser,Depends(require_admin)],system_ids:Annotated[list[int]|None,Form()]=None,employee_ids:Annotated[list[int]|None,Form()]=None):
    cargo=session.get(Cargo,cargo_id)
    if not cargo: raise HTTPException(404,'Cargo nao encontrado')
    valid_systems=set(session.scalars(select(SistemaCorporativo.id).where(SistemaCorporativo.id.in_(set(system_ids or [-1])))).all())
    valid_employees=set(session.scalars(select(Funcionario.id).where(Funcionario.id.in_(set(employee_ids or [-1])),Funcionario.departamento_id==cargo.departamento_id)).all())
    session.query(CargoSistema).filter(CargoSistema.cargo_id==cargo.id).delete()
    session.add_all(CargoSistema(cargo_id=cargo.id,sistema_id=value) for value in valid_systems)
    session.query(FuncionarioCargo).filter(FuncionarioCargo.cargo_id==cargo.id).delete()
    session.add_all(FuncionarioCargo(cargo_id=cargo.id,funcionario_id=value) for value in valid_employees)
    session.commit(); return RedirectResponse(f'/admin/departamentos/{cargo.departamento_id}',status_code=303)

@router.get('/admin/sistemas', response_class=HTMLResponse)
def cadastros_sistemas(request:Request,session:Db,user:Annotated[SystemUser,Depends(require_admin)]):
    systems=session.scalars(select(SistemaCorporativo).order_by(SistemaCorporativo.nome)).all()
    return templates.TemplateResponse(request=request,name='systems.html',context={'user':user,'systems':systems})

@router.post('/admin/sistemas')
def cadastros_sistema_criar(session:Db,user:Annotated[SystemUser,Depends(require_admin)],nome:Annotated[str,Form()],descricao:Annotated[str,Form()]=''):
    value=nome.strip()
    if not value: raise HTTPException(400,'Informe o nome do sistema')
    if session.scalar(select(SistemaCorporativo).where(func.lower(SistemaCorporativo.nome)==value.lower())): raise HTTPException(409,'Sistema ja cadastrado')
    session.add(SistemaCorporativo(nome=value,descricao=descricao.strip() or None,ativo=True));session.commit()
    return RedirectResponse('/admin/sistemas',status_code=303)

# MENU_DEPARTAMENTOS_E_EDICAO_V1
@router.get('/admin/departamentos/{department_id}/editar', response_class=HTMLResponse)
def cadastros_departamento_editar_pagina(
    request: Request,
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    return templates.TemplateResponse(
        request=request,
        name='department_edit.html',
        context={'user': user, 'department': department, 'error': None},
    )


@router.post('/admin/departamentos/{department_id}/editar', response_class=HTMLResponse)
def cadastros_departamento_editar_salvar(
    request: Request,
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    nome: Annotated[str, Form()],
    ativo: Annotated[str | None, Form()] = None,
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    normalized_name = nome.strip()
    error = None
    if not normalized_name:
        error = 'Informe o nome do departamento.'
    elif session.scalar(
        select(Departamento).where(
            func.lower(Departamento.nome) == normalized_name.lower(),
            Departamento.id != department.id,
        )
    ):
        error = 'Ja existe outro departamento com este nome.'
    if error:
        return templates.TemplateResponse(
            request=request,
            name='department_edit.html',
            context={'user': user, 'department': department, 'error': error},
            status_code=409,
        )
    department.nome = normalized_name
    department.ativo = ativo == 'on'
    session.commit()
    return RedirectResponse(f'/admin/departamentos/{department.id}', status_code=303)

# DEPARTAMENTOS_SEPARACAO_ARVORE_CADASTRO_V2
@router.get('/portal/departamentos', response_class=HTMLResponse)
def departamentos_arvore_portal(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
):
    query = select(Departamento).where(Departamento.ativo.is_(True)).order_by(Departamento.nome)
    if user.role == ROLE_MANAGER:
        query = query.where(Departamento.id == user.department_id)
    departments = session.scalars(query).all()
    department_ids = [item.id for item in departments]
    cargos = session.scalars(
        select(Cargo)
        .where(Cargo.departamento_id.in_(department_ids or [-1]), Cargo.ativo.is_(True))
        .order_by(Cargo.nome)
    ).all()
    cargos_by_department = {item.id: [] for item in departments}
    systems_by_cargo = {item.id: [] for item in cargos}
    users_by_cargo = {item.id: [] for item in cargos}
    for cargo in cargos:
        cargos_by_department.setdefault(cargo.departamento_id, []).append(cargo)
    if cargos:
        cargo_ids = [item.id for item in cargos]
        for cargo_id, system in session.execute(
            select(CargoSistema.cargo_id, SistemaCorporativo)
            .join(SistemaCorporativo, SistemaCorporativo.id == CargoSistema.sistema_id)
            .where(CargoSistema.cargo_id.in_(cargo_ids))
            .order_by(SistemaCorporativo.nome)
        ):
            systems_by_cargo[cargo_id].append(system)
        for cargo_id, employee in session.execute(
            select(FuncionarioCargo.cargo_id, Funcionario)
            .join(Funcionario, Funcionario.id == FuncionarioCargo.funcionario_id)
            .where(FuncionarioCargo.cargo_id.in_(cargo_ids))
            .order_by(Funcionario.nome)
        ):
            users_by_cargo[cargo_id].append(employee)
    return templates.TemplateResponse(
        request=request,
        name='departments_tree.html',
        context={
            'user': user,
            'departments': departments,
            'cargos_by_department': cargos_by_department,
            'systems_by_cargo': systems_by_cargo,
            'users_by_cargo': users_by_cargo,
        },
    )


@router.get('/admin/cadastros/departamentos/{department_id}', response_class=HTMLResponse)
def departamento_cadastro_detalhe_v2(
    request: Request,
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    cargos = session.scalars(
        select(Cargo).where(Cargo.departamento_id == department_id).order_by(Cargo.nome)
    ).all()
    employees = session.scalars(
        select(Funcionario).where(Funcionario.departamento_id == department_id).order_by(Funcionario.nome)
    ).all()
    systems = session.scalars(
        select(SistemaCorporativo).where(SistemaCorporativo.ativo.is_(True)).order_by(SistemaCorporativo.nome)
    ).all()
    assignments = {
        employee.id: set(session.scalars(
            select(FuncionarioCargo.cargo_id).where(FuncionarioCargo.funcionario_id == employee.id)
        ).all())
        for employee in employees
    }
    systems_by_cargo = {
        cargo.id: set(session.scalars(
            select(CargoSistema.sistema_id).where(CargoSistema.cargo_id == cargo.id)
        ).all())
        for cargo in cargos
    }
    return templates.TemplateResponse(
        request=request,
        name='department_manage.html',
        context={
            'user': user,
            'department': department,
            'cargos': cargos,
            'employees': employees,
            'systems': systems,
            'assignments': assignments,
            'systems_by_cargo': systems_by_cargo,
        },
    )


@router.get('/admin/cadastros/departamentos/{department_id}/editar', response_class=HTMLResponse)
def departamento_editar_v2_page(
    request: Request,
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    return templates.TemplateResponse(
        request=request,
        name='department_edit_v2.html',
        context={'user': user, 'department': department, 'error': None},
    )


@router.post('/admin/cadastros/departamentos/{department_id}/editar', response_class=HTMLResponse)
def departamento_editar_v2_save(
    request: Request,
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    nome: Annotated[str, Form()],
    ativo: Annotated[str | None, Form()] = None,
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    value = nome.strip()
    duplicate = session.scalar(
        select(Departamento).where(
            func.lower(Departamento.nome) == value.lower(),
            Departamento.id != department.id,
        )
    ) if value else None
    error = 'Informe o nome do departamento.' if not value else ('Ja existe outro departamento com este nome.' if duplicate else None)
    if error:
        return templates.TemplateResponse(
            request=request,
            name='department_edit_v2.html',
            context={'user': user, 'department': department, 'error': error},
            status_code=409,
        )
    department.nome = value
    department.ativo = ativo == 'on'
    session.commit()
    return RedirectResponse(f'/admin/cadastros/departamentos/{department.id}', status_code=303)


@router.post('/admin/cadastros/departamentos/{department_id}/cargos')
def departamento_cargo_criar_v2(
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    nome: Annotated[str, Form()],
    descricao: Annotated[str, Form()] = '',
    observacao: Annotated[str, Form()] = '',
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    value = nome.strip()
    if not value:
        raise HTTPException(400, 'Informe o nome do cargo')
    if session.scalar(select(Cargo).where(Cargo.departamento_id == department_id, func.lower(Cargo.nome) == value.lower())):
        raise HTTPException(409, 'Cargo ja cadastrado neste departamento')
    session.add(Cargo(
        departamento_id=department_id,
        nome=value,
        descricao=descricao.strip() or None,
        observacao=observacao.strip() or None,
        ativo=True,
    ))
    session.commit()
    return RedirectResponse(f'/admin/cadastros/departamentos/{department_id}', status_code=303)


@router.post('/admin/cadastros/cargos/{cargo_id}/sistemas')
def cargo_sistemas_salvar_v2(
    cargo_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    system_ids: Annotated[list[int] | None, Form()] = None,
):
    cargo = session.get(Cargo, cargo_id)
    if not cargo:
        raise HTTPException(404, 'Cargo nao encontrado')
    valid = set(session.scalars(
        select(SistemaCorporativo.id).where(SistemaCorporativo.id.in_(set(system_ids or [-1])))
    ).all())
    session.query(CargoSistema).filter(CargoSistema.cargo_id == cargo.id).delete()
    session.add_all(CargoSistema(cargo_id=cargo.id, sistema_id=value) for value in valid)
    session.commit()
    return RedirectResponse(f'/admin/cadastros/departamentos/{cargo.departamento_id}', status_code=303)


@router.post('/admin/cadastros/departamentos/{department_id}/funcionarios/{employee_id}/cargo')
def funcionario_cargo_salvar_v2(
    department_id: int,
    employee_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    cargo_id: Annotated[int | None, Form()] = None,
):
    employee = session.get(Funcionario, employee_id)
    if not employee or employee.departamento_id != department_id:
        raise HTTPException(404, 'Funcionario nao encontrado neste departamento')
    session.query(FuncionarioCargo).filter(FuncionarioCargo.funcionario_id == employee.id).delete()
    if cargo_id:
        cargo = session.get(Cargo, cargo_id)
        if not cargo or cargo.departamento_id != department_id:
            raise HTTPException(400, 'Cargo invalido para este departamento')
        session.add(FuncionarioCargo(funcionario_id=employee.id, cargo_id=cargo.id))
    session.commit()
    return RedirectResponse(f'/admin/cadastros/departamentos/{department_id}#funcionarios', status_code=303)

# CADASTRO_DEPARTAMENTO_TRANSFERENCIA_V3
@router.get('/admin/cadastros/departamentos/{department_id}/painel', response_class=HTMLResponse)
def departamento_painel_v3(
    request: Request,
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    aba: str = 'usuarios',
    cargo_id: int | None = None,
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    cargos = session.scalars(
        select(Cargo).where(Cargo.departamento_id == department_id).order_by(Cargo.nome)
    ).all()
    all_employees = session.scalars(select(Funcionario).order_by(Funcionario.nome)).all()
    linked_ids = set(session.scalars(
        select(FuncionarioDepartamento.funcionario_id).where(
            FuncionarioDepartamento.departamento_id == department_id
        )
    ).all())
    # Compatibilidade com o departamento principal ja existente.
    linked_ids.update(session.scalars(
        select(Funcionario.id).where(Funcionario.departamento_id == department_id)
    ).all())
    linked_employees = [item for item in all_employees if item.id in linked_ids]
    available_employees = [item for item in all_employees if item.id not in linked_ids]
    selected_cargo = session.get(Cargo, cargo_id) if cargo_id else None
    if selected_cargo and selected_cargo.departamento_id != department_id:
        raise HTTPException(400, 'Cargo fora do departamento')
    cargo_user_ids = set()
    cargo_system_ids = set()
    if selected_cargo:
        cargo_user_ids = set(session.scalars(
            select(FuncionarioCargo.funcionario_id).where(FuncionarioCargo.cargo_id == selected_cargo.id)
        ).all())
        cargo_system_ids = set(session.scalars(
            select(CargoSistema.sistema_id).where(CargoSistema.cargo_id == selected_cargo.id)
        ).all())
    cargo_users = [item for item in linked_employees if item.id in cargo_user_ids]
    cargo_available_users = [item for item in linked_employees if item.id not in cargo_user_ids]
    systems = session.scalars(
        select(SistemaCorporativo).where(SistemaCorporativo.ativo.is_(True)).order_by(SistemaCorporativo.nome)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name='department_manage_v3.html',
        context={
            'user': user,
            'department': department,
            'aba': aba if aba in {'usuarios', 'cargos'} else 'usuarios',
            'cargos': cargos,
            'selected_cargo': selected_cargo,
            'available_employees': available_employees,
            'linked_employees': linked_employees,
            'cargo_available_users': cargo_available_users,
            'cargo_users': cargo_users,
            'systems': systems,
            'cargo_system_ids': cargo_system_ids,
        },
    )


@router.post('/admin/cadastros/departamentos/{department_id}/usuarios')
def departamento_usuarios_sync_v3(
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    employee_ids: Annotated[list[int] | None, Form()] = None,
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    requested = set(employee_ids or [])
    valid = set(session.scalars(
        select(Funcionario.id).where(Funcionario.id.in_(requested or {-1}))
    ).all())
    current = set(session.scalars(
        select(FuncionarioDepartamento.funcionario_id).where(
            FuncionarioDepartamento.departamento_id == department_id
        )
    ).all())
    session.query(FuncionarioDepartamento).filter(
        FuncionarioDepartamento.departamento_id == department_id
    ).delete(synchronize_session=False)
    session.add_all(
        FuncionarioDepartamento(funcionario_id=employee_id, departamento_id=department_id)
        for employee_id in valid
    )
    removed = current - valid
    if removed:
        cargo_ids = set(session.scalars(
            select(Cargo.id).where(Cargo.departamento_id == department_id)
        ).all())
        if cargo_ids:
            session.query(FuncionarioCargo).filter(
                FuncionarioCargo.funcionario_id.in_(removed),
                FuncionarioCargo.cargo_id.in_(cargo_ids),
            ).delete(synchronize_session=False)
    session.commit()
    return RedirectResponse(
        f'/admin/cadastros/departamentos/{department_id}/painel?aba=usuarios',
        status_code=303,
    )


@router.post('/admin/cadastros/departamentos/{department_id}/cargos/v3')
def departamento_cargo_save_v3(
    department_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    nome: Annotated[str, Form()],
    cargo_id: Annotated[int | None, Form()] = None,
    descricao: Annotated[str, Form()] = '',
    observacao: Annotated[str, Form()] = '',
    ativo: Annotated[str | None, Form()] = None,
):
    department = session.get(Departamento, department_id)
    if not department:
        raise HTTPException(404, 'Departamento nao encontrado')
    value = nome.strip()
    if not value:
        raise HTTPException(400, 'Informe o nome do cargo')
    duplicate_query = select(Cargo).where(
        Cargo.departamento_id == department_id,
        func.lower(Cargo.nome) == value.lower(),
    )
    if cargo_id:
        duplicate_query = duplicate_query.where(Cargo.id != cargo_id)
    if session.scalar(duplicate_query):
        raise HTTPException(409, 'Ja existe outro cargo com este nome no departamento')
    if cargo_id:
        cargo = session.get(Cargo, cargo_id)
        if not cargo or cargo.departamento_id != department_id:
            raise HTTPException(404, 'Cargo nao encontrado')
    else:
        cargo = Cargo(departamento_id=department_id)
        session.add(cargo)
    cargo.nome = value
    cargo.descricao = descricao.strip() or None
    cargo.observacao = observacao.strip() or None
    cargo.ativo = ativo == 'on' if cargo_id else True
    session.commit()
    return RedirectResponse(
        f'/admin/cadastros/departamentos/{department_id}/painel?aba=cargos',
        status_code=303,
    )


@router.post('/admin/cadastros/departamentos/{department_id}/cargos/{cargo_id}/vinculos-v3')
def cargo_vinculos_sync_v3(
    department_id: int,
    cargo_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    employee_ids: Annotated[list[int] | None, Form()] = None,
    system_ids: Annotated[list[int] | None, Form()] = None,
):
    cargo = session.get(Cargo, cargo_id)
    if not cargo or cargo.departamento_id != department_id:
        raise HTTPException(404, 'Cargo nao encontrado no departamento')
    department_employee_ids = set(session.scalars(
        select(FuncionarioDepartamento.funcionario_id).where(
            FuncionarioDepartamento.departamento_id == department_id
        )
    ).all())
    department_employee_ids.update(session.scalars(
        select(Funcionario.id).where(Funcionario.departamento_id == department_id)
    ).all())
    valid_employees = set(employee_ids or []) & department_employee_ids
    valid_systems = set(session.scalars(
        select(SistemaCorporativo.id).where(
            SistemaCorporativo.id.in_(set(system_ids or []) or {-1})
        )
    ).all())
    session.query(FuncionarioCargo).filter(FuncionarioCargo.cargo_id == cargo_id).delete(
        synchronize_session=False
    )
    session.add_all(
        FuncionarioCargo(funcionario_id=employee_id, cargo_id=cargo_id)
        for employee_id in valid_employees
    )
    session.query(CargoSistema).filter(CargoSistema.cargo_id == cargo_id).delete(
        synchronize_session=False
    )
    session.add_all(
        CargoSistema(cargo_id=cargo_id, sistema_id=system_id)
        for system_id in valid_systems
    )
    session.commit()
    return RedirectResponse(
        f'/admin/cadastros/departamentos/{department_id}/painel?aba=cargos&cargo_id={cargo_id}',
        status_code=303,
    )

# MANUTENCAO_DEPARTAMENTOS_CARGOS_V4
