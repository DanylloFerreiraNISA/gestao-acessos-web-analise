from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlparse

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
    elif new_password and len(new_password) < 10:
        error = 'A nova senha precisa ter pelo menos 10 caracteres.'

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


@router.get('/portal/perfis', response_class=HTMLResponse)
def portal_profiles(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    query = select(Perfil).order_by(Perfil.nome)
    if user.role == ROLE_MANAGER:
        query = query.where(Perfil.id.in_(profile_ids_for_department(session, user.department_id)))
    return templates.TemplateResponse(request=request, name='portal_profiles.html', context={'user': user, 'profiles': session.scalars(query).all()})


@router.get('/portal/perfis/{profile_id}', response_class=HTMLResponse)
def portal_profile_detail(request: Request, profile_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    profile = session.get(Perfil, profile_id)
    if not profile:
        raise HTTPException(404, 'Perfil nao encontrado')
    if user.role == ROLE_MANAGER:
        allowed = session.scalar(select(func.count()).select_from(FuncionarioPerfil).join(Funcionario).where(FuncionarioPerfil.perfil_id == profile_id, Funcionario.departamento_id == user.department_id))
        if not allowed:
            raise HTTPException(403, 'Perfil fora do departamento')
    return templates.TemplateResponse(request=request, name='portal_profile.html', context={'user': user, 'profile': profile})


@router.get('/admin/contas', response_class=HTMLResponse)
def accounts(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_admin)]):
    users = session.scalars(select(SystemUser).options(selectinload(SystemUser.department)).order_by(SystemUser.name)).all()
    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all()
    return templates.TemplateResponse(request=request, name='accounts.html', context={'user': user, 'users': users, 'departments': departments})


@router.post('/admin/contas')
def account_create(session: Db, user: Annotated[SystemUser, Depends(require_admin)], name: Annotated[str, Form()], username: Annotated[str, Form()], email: Annotated[str, Form()], password: Annotated[str, Form()], role: Annotated[str, Form()], department_id: Annotated[int | None, Form()] = None):
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
    create_history(session, proposal.id, user.id, mapping[action], details.strip() or None)
    session.commit(); return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)
