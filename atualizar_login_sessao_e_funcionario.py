from pathlib import Path
import py_compile

ROOT = Path.cwd()
APP = ROOT / 'app'
ACCESS = APP / 'access_control.py'
MAIN = APP / 'main.py'
T = APP / 'templates'
S = APP / 'static'

for required in (ACCESS, MAIN, T/'base.html', T/'login.html', T/'funcionario.html'):
    if not required.exists():
        raise SystemExit(f'Arquivo nao encontrado: {required}')

text = ACCESS.read_text(encoding='utf-8')

# Imports necessários.
text = text.replace(
    'from datetime import datetime, timezone',
    'from datetime import datetime, timedelta, timezone'
)
if 'from urllib.parse import urlparse' not in text:
    text = text.replace('from typing import Annotated', 'from typing import Annotated\nfrom urllib.parse import urlparse')

# Configuração central da sessão.
config_marker = "ROLE_ANALYST = 'ANALISTA_TI'"
config = """
SESSION_IDLE_MINUTES = int(os.getenv('SESSION_IDLE_MINUTES', '10'))
MAX_CONCURRENT_SESSIONS = int(os.getenv('MAX_CONCURRENT_SESSIONS', '2'))
SESSION_ABSOLUTE_HOURS = int(os.getenv('SESSION_ABSOLUTE_HOURS', '10'))
"""
if 'SESSION_IDLE_MINUTES =' not in text:
    text = text.replace(config_marker, config_marker + config)

# Username no modelo.
email_line = "    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)\n"
if 'username: Mapped[' not in text:
    text = text.replace(email_line, email_line + "    username: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)\n", 1)

# Auditoria de atividade na sessão.
expires_line = "    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))\n"
if 'last_activity_at: Mapped[' not in text:
    text = text.replace(
        expires_line,
        expires_line + "    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))\n    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)\n",
        1,
    )

# Helper seguro para retorno após autenticação.
helper_anchor = 'def hash_password(password: str) -> str:'
helpers = '''def safe_next_url(value: str | None) -> str:\n    if not value:\n        return '/portal'\n    parsed = urlparse(value)\n    if parsed.scheme or parsed.netloc or not value.startswith('/') or value.startswith('//'):\n        return '/portal'\n    return value\n\n\ndef normalize_username(value: str) -> str:\n    username = value.strip().lower()\n    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789._-')\n    if not username or any(char not in allowed for char in username):\n        raise HTTPException(400, 'Usuario invalido. Use letras, numeros, ponto, hifen ou sublinhado.')\n    return username\n\n\n'''
if 'def safe_next_url(' not in text:
    text = text.replace(helper_anchor, helpers + helper_anchor, 1)

# Login GET com parâmetro next.
old_get = """@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request, user: Annotated[SystemUser | None, Depends(current_user_optional)]):
    if user: return RedirectResponse('/portal', status_code=303)
    return templates.TemplateResponse(request=request, name='login.html', context={'error': None})
"""
new_get = """@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request, user: Annotated[SystemUser | None, Depends(current_user_optional)], next: str | None = None, reason: str | None = None):
    destination = safe_next_url(next)
    if user:
        return RedirectResponse(destination, status_code=303)
    message = 'Sua sessao expirou por inatividade. Entre novamente.' if reason == 'inactive' else None
    return templates.TemplateResponse(request=request, name='login.html', context={'error': message, 'next_url': destination})
"""
if old_get in text:
    text = text.replace(old_get, new_get, 1)

# Substitui rota POST /login por versão completa.
start = text.find("@router.post('/login', response_class=HTMLResponse)")
end = text.find("\n@router.post('/logout')", start)
if start < 0 or end < 0:
    raise SystemExit('Rotas de login/logout nao encontradas.')
login_route = '''@router.post('/login', response_class=HTMLResponse)\ndef login(request: Request, session: Db, login: Annotated[str, Form()], password: Annotated[str, Form()], next_url: Annotated[str, Form()] = '/portal'):\n    identifier = login.strip().lower()\n    user = session.scalar(\n        select(SystemUser).where(\n            (func.lower(SystemUser.email) == identifier)\n            | (func.lower(SystemUser.username) == identifier)\n        )\n    )\n    destination = safe_next_url(next_url)\n    if not user or not user.active or not verify_password(password, user.password_hash):\n        return templates.TemplateResponse(\n            request=request,\n            name='login.html',\n            context={'error': 'E-mail, usuario ou senha invalidos', 'next_url': destination},\n            status_code=401,\n        )\n\n    now = datetime.now(timezone.utc)\n    # Remove sessões vencidas antes de aplicar o limite simultâneo.\n    session.execute(\n        delete(LoginSession).where(\n            (LoginSession.user_id == user.id)\n            & (\n                (LoginSession.expires_at <= now)\n                | (LoginSession.last_activity_at <= now - timedelta(minutes=SESSION_IDLE_MINUTES))\n            )\n        )\n    )\n    active_sessions = session.scalars(\n        select(LoginSession)\n        .where(LoginSession.user_id == user.id)\n        .order_by(LoginSession.last_activity_at.asc(), LoginSession.id.asc())\n    ).all()\n    # Política escolhida: permite o novo acesso e encerra as sessões mais antigas.\n    overflow = max(0, len(active_sessions) - MAX_CONCURRENT_SESSIONS + 1)\n    for old_session in active_sessions[:overflow]:\n        session.delete(old_session)\n\n    raw = secrets.token_urlsafe(48)\n    session.add(\n        LoginSession(\n            token_hash=hashlib.sha256(raw.encode()).hexdigest(),\n            user_id=user.id,\n            created_at=now,\n            last_activity_at=now,\n            expires_at=now + timedelta(hours=SESSION_ABSOLUTE_HOURS),\n        )\n    )\n    session.commit()\n    response = RedirectResponse(destination, status_code=303)\n    response.set_cookie(\n        'access_session',\n        raw,\n        httponly=True,\n        samesite='lax',\n        secure=False,\n        max_age=SESSION_ABSOLUTE_HOURS * 3600,\n    )\n    return response\n'''
text = text[:start] + login_route + text[end:]

# current_user_optional aplica idle timeout e renova last_activity.
start = text.find('def current_user_optional(')
end = text.find('\n\ndef require_user(', start)
if start < 0 or end < 0:
    raise SystemExit('current_user_optional nao encontrada.')
current_user = '''def current_user_optional(request: Request, session: Db) -> SystemUser | None:\n    token = request.cookies.get('access_session')\n    if not token:\n        return None\n    token_hash = hashlib.sha256(token.encode()).hexdigest()\n    login = session.scalar(\n        select(LoginSession)\n        .options(selectinload(LoginSession.user).selectinload(SystemUser.department))\n        .where(LoginSession.token_hash == token_hash)\n    )\n    if not login:\n        return None\n    now = datetime.now(timezone.utc)\n    idle_limit = now - timedelta(minutes=SESSION_IDLE_MINUTES)\n    if login.expires_at <= now or login.last_activity_at <= idle_limit or not login.user.active:\n        session.delete(login)\n        session.commit()\n        return None\n    login.last_activity_at = now\n    session.commit()\n    return login.user\n'''
text = text[:start] + current_user + text[end:]

# Endpoint de atividade, usado somente quando houve interação real na página.
activity_route = '''\n\n@router.post('/session/activity')\ndef session_activity(request: Request, session: Db):\n    token = request.cookies.get('access_session')\n    if not token:\n        raise HTTPException(401, 'Sessao inexistente')\n    login = session.scalar(select(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))\n    if not login:\n        raise HTTPException(401, 'Sessao inexistente')\n    now = datetime.now(timezone.utc)\n    if login.expires_at <= now or login.last_activity_at <= now - timedelta(minutes=SESSION_IDLE_MINUTES):\n        session.delete(login)\n        session.commit()\n        raise HTTPException(401, 'Sessao expirada')\n    login.last_activity_at = now\n    session.commit()\n    return {'ok': True}\n'''
if "@router.post('/session/activity')" not in text:
    logout_pos = text.find("@router.post('/logout')")
    text = text[:logout_pos] + activity_route + '\n\n' + text[logout_pos:]

# Middleware: next e motivo de inatividade.
text = text.replace(
    "return RedirectResponse('/login', status_code=303)",
    "return RedirectResponse(f'/login?next={request.url.path}&reason=inactive', status_code=303)",
)
# Evita que o middleware trate heartbeat como rota pública inexistente.
text = text.replace(
    "PUBLIC_PATHS = {'/login', '/health'}",
    "PUBLIC_PATHS = {'/login', '/health', '/session/activity'}",
)

# Username na criação de contas, caso ainda falte.
old_signature = "def account_create(session: Db, user: Annotated[SystemUser, Depends(require_admin)], name: Annotated[str, Form()], email: Annotated[str, Form()], password: Annotated[str, Form()], role: Annotated[str, Form()], department_id: Annotated[int | None, Form()] = None):"
new_signature = "def account_create(session: Db, user: Annotated[SystemUser, Depends(require_admin)], name: Annotated[str, Form()], username: Annotated[str, Form()], email: Annotated[str, Form()], password: Annotated[str, Form()], role: Annotated[str, Form()], department_id: Annotated[int | None, Form()] = None):"
text = text.replace(old_signature, new_signature)
old_add = "session.add(SystemUser(name=name.strip(), email=email.strip().lower(), password_hash=hash_password(password), role=role, department_id=department_id, active=True))"
new_add = "session.add(SystemUser(name=name.strip(), username=normalize_username(username), email=email.strip().lower(), password_hash=hash_password(password), role=role, department_id=department_id, active=True))"
text = text.replace(old_add, new_add)

# Rotas de edição de funcionário, se ainda não existem.
if "@router.get('/portal/funcionarios/{employee_id}/editar'" not in text:
    edit_routes = r'''

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
'''
    marker = "@router.get('/portal/propostas'"
    pos = text.find(marker)
    if pos < 0:
        raise SystemExit('Ponto para rotas de edicao nao encontrado.')
    text = text[:pos] + edit_routes + '\n\n' + text[pos:]

ACCESS.write_text(text, encoding='utf-8', newline='\n')

# Login visual.
login_html = '''{% extends "base.html" %}{% block title %}Entrar | Gestao de Acessos{% endblock %}{% block content %}<section class="auth-shell"><form class="auth-card" method="post"><div class="auth-mark">GA</div><h1>Gestao de Acessos</h1><p>Entre com seu e-mail corporativo ou nome de usuario.</p>{% if error %}<div class="alert error">{{ error }}</div>{% endif %}<input type="hidden" name="next_url" value="{{ next_url or '/portal' }}"><label>E-mail ou usuario<input name="login" type="text" autocomplete="username" placeholder="nome@empresa.com ou danyllo.ferreira" required autofocus></label><label>Senha<input name="password" type="password" autocomplete="current-password" required></label><button class="primary wide">Entrar</button><small>Por seguranca, a sessao encerra apos 10 minutos sem atividade.</small></form></section>{% endblock %}'''
(T/'login.html').write_text(login_html, encoding='utf-8', newline='\n')

# Formulário de contas com username.
accounts = T/'accounts.html'
if accounts.exists():
    html = accounts.read_text(encoding='utf-8')
    if 'name="username"' not in html:
        html = html.replace('<input name="name" placeholder="Nome" required>', '<input name="name" placeholder="Nome" required><input name="username" placeholder="Usuario, ex.: danyllo.ferreira" pattern="[A-Za-z0-9._-]+" required>')
    accounts.write_text(html, encoding='utf-8', newline='\n')

# Formulário de edição.
edit_html = '''{% extends "base.html" %}{% block title %}Editar {{ employee.nome }}{% endblock %}{% block content %}<a class="back" href="/funcionarios/{{ employee.id }}">Voltar para o usuario</a><section class="hero compact"><p class="eyebrow">Cadastro de funcionario</p><h1>Editar funcionario</h1><p>{% if user.role == 'GESTOR_DEPARTAMENTO' %}Alteracoes restritas a {{ user.department.nome }}.{% else %}Edicao administrativa.{% endif %}</p></section><form class="panel integrated-form employee-edit-form" method="post">{% if error %}<div class="alert error full">{{ error }}</div>{% endif %}<label>Nome<input name="name" value="{{ employee.nome }}" required></label><label>Login do funcionario<input name="login" value="{{ employee.login }}" pattern="[^\\s]+" required></label><label>Departamento<select name="department_id" required {% if user.role == 'GESTOR_DEPARTAMENTO' %}disabled{% endif %}>{% for department in departments %}<option value="{{ department.id }}" {% if department.id == employee.departamento_id %}selected{% endif %}>{{ department.nome }}</option>{% endfor %}</select>{% if user.role == 'GESTOR_DEPARTAMENTO' %}<input type="hidden" name="department_id" value="{{ employee.departamento_id }}"><small>Somente a T.I. pode transferir o departamento.</small>{% endif %}</label><label class="checkbox-field"><input type="checkbox" name="active" {% if employee.ativo %}checked{% endif %}> Funcionario ativo</label><div class="full form-actions"><a class="secondary-button" href="/funcionarios/{{ employee.id }}">Cancelar</a><button class="primary">Salvar alteracoes</button></div></form>{% endblock %}'''
(T/'portal_employee_edit.html').write_text(edit_html, encoding='utf-8', newline='\n')

# Botão sem substituir a tela aprovada.
funcionario = T/'funcionario.html'
html = funcionario.read_text(encoding='utf-8')
if '/portal/funcionarios/{{ funcionario.id }}/editar' not in html:
    button = '<div class="employee-page-actions"><a class="button" href="/portal/funcionarios/{{ funcionario.id }}/editar">Editar funcionario</a></div>'
    pos = html.find('</section>')
    if pos >= 0:
        pos += len('</section>')
        html = html[:pos] + button + html[pos:]
    funcionario.write_text(html, encoding='utf-8', newline='\n')

# Script de inatividade. Só renova no servidor quando houve interação do usuário.
activity_js = r'''(()=>{const IDLE_MS=10*60*1000;let last=Date.now(),lastPing=0,timer;const loginUrl=()=>`/login?next=${encodeURIComponent(location.pathname+location.search)}&reason=inactive`;function schedule(){clearTimeout(timer);timer=setTimeout(()=>location.replace(loginUrl()),Math.max(0,IDLE_MS-(Date.now()-last)))}async function active(){last=Date.now();schedule();if(Date.now()-lastPing<60000)return;lastPing=Date.now();try{const r=await fetch('/session/activity',{method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'}});if(r.status===401)location.replace(loginUrl())}catch(_){}}['click','keydown','mousemove','scroll','touchstart'].forEach(e=>addEventListener(e,active,{passive:true}));schedule()})();'''
(S/'session-activity.js').write_text(activity_js, encoding='utf-8', newline='\n')
base = T/'base.html'
base_html = base.read_text(encoding='utf-8')
script = '<script src="{{ url_for(\'static\', path=\'/session-activity.js\') }}"></script>'
if 'session-activity.js' not in base_html:
    base_html = base_html.replace('{% block scripts %}', script + '{% block scripts %}')
base.write_text(base_html, encoding='utf-8', newline='\n')

# Migração PostgreSQL idempotente.
migration = r'''from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from app.database import engine
from app.access_control import LoginSession, SystemUser

with engine.begin() as connection:
    user_columns = {c['name'] for c in inspect(connection).get_columns('system_users')}
    if 'username' not in user_columns:
        connection.execute(text('ALTER TABLE system_users ADD COLUMN username VARCHAR(120)'))
    connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_system_users_username ON system_users (username)'))
    session_columns = {c['name'] for c in inspect(connection).get_columns('login_sessions')}
    if 'created_at' not in session_columns:
        connection.execute(text('ALTER TABLE login_sessions ADD COLUMN created_at TIMESTAMPTZ'))
    if 'last_activity_at' not in session_columns:
        connection.execute(text('ALTER TABLE login_sessions ADD COLUMN last_activity_at TIMESTAMPTZ'))
    connection.execute(text('UPDATE login_sessions SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP), last_activity_at = COALESCE(last_activity_at, CURRENT_TIMESTAMP)'))
    connection.execute(text('ALTER TABLE login_sessions ALTER COLUMN created_at SET NOT NULL'))
    connection.execute(text('ALTER TABLE login_sessions ALTER COLUMN last_activity_at SET NOT NULL'))
    connection.execute(text('CREATE INDEX IF NOT EXISTS ix_login_sessions_last_activity_at ON login_sessions (last_activity_at)'))

with Session(engine) as session:
    users = session.scalars(select(SystemUser).order_by(SystemUser.id)).all()
    used = {u.username.lower() for u in users if u.username}
    for user in users:
        if user.username:
            continue
        base = ''.join(c for c in user.email.split('@',1)[0].lower() if c in 'abcdefghijklmnopqrstuvwxyz0123456789._-') or f'usuario{user.id}'
        candidate, suffix = base, 2
        while candidate in used:
            candidate, suffix = f'{base}.{suffix}', suffix + 1
        user.username = candidate
        used.add(candidate)
        print(f'{user.email} -> {candidate}')
    session.commit()
print('Migracao concluida.')
'''
(ROOT/'migrar_seguranca_sessao.py').write_text(migration, encoding='utf-8', newline='\n')

# CSS mínimo.
styles = S/'styles.css'
css = styles.read_text(encoding='utf-8')
if '/* SESSAO_E_EDICAO_V2 */' not in css:
    css += '\n/* SESSAO_E_EDICAO_V2 */\n.employee-page-actions{display:flex;justify-content:flex-end;margin:-6px 0 12px}.checkbox-field{display:flex!important;align-items:center;gap:8px}.form-actions{display:flex;justify-content:flex-end;gap:8px}.secondary-button{padding:9px 13px;border-radius:7px;background:#e7edf3;color:#17365d;text-decoration:none}.auth-card small{color:#667085}\n'
styles.write_text(css, encoding='utf-8', newline='\n')

py_compile.compile(str(ACCESS), doraise=True)
py_compile.compile(str(MAIN), doraise=True)
print('Atualizacao cumulativa aplicada.')
print('Execute agora: python .\\migrar_seguranca_sessao.py')
print('Limite simultaneo padrao: 2 sessoes por conta.')
print('Inatividade: 10 minutos.')
