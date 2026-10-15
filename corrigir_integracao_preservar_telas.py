from pathlib import Path
import py_compile

ROOT = Path.cwd()
APP = ROOT / 'app'
T = APP / 'templates'
S = APP / 'static'
MAIN = APP / 'main.py'
ACCESS = APP / 'access_control.py'

for required in (MAIN, ACCESS, T/'base.html', T/'funcionario.html', T/'perfil.html'):
    if not required.exists():
        raise SystemExit(f'Arquivo nao encontrado: {required}')

# 1. Base unica: identifica usuario pela request.state, inclusive nas telas antigas.
base = '''<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}Gestao de Acessos{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', path='/styles.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', path='/portal.css') }}">
  {% block head %}{% endblock %}
</head>
<body>
{% set current_user = user if user is defined and user else request.state.current_user if request.state.current_user is defined else none %}
<header class="topbar">
  <a class="brand" href="{{ '/portal' if current_user else '/login' }}">Gestao de Acessos</a>
  <nav>
    {% if current_user %}
      <a href="/portal">Inicio</a>
      <a href="/portal/funcionarios">Usuarios</a>
      <a href="/portal/perfis">Perfis</a>
      <a href="/portal/propostas">Propostas</a>
      {% if current_user.role in ['ADMIN_TI','ANALISTA_TI'] %}
        <a href="/comparar">Comparar</a>
        <a href="/admin/contas">Contas</a>
      {% endif %}
      <span class="nav-scope">{{ current_user.department.nome if current_user.department else 'T.I. - Todos os departamentos' }}</span>
      <form action="/logout" method="post" class="logout-form"><button type="submit">Sair</button></form>
    {% else %}
      <a href="/login">Entrar</a>
    {% endif %}
  </nav>
</header>
<main class="container">{% block content %}{% endblock %}</main>
<script src="{{ url_for('static', path='/classic-tree.js') }}"></script>
<script src="{{ url_for('static', path='/comparison.js') }}"></script>
{% block scripts %}{% endblock %}
</body>
</html>
'''
(T/'base.html').write_text(base, encoding='utf-8', newline='\n')

# 2. A lista autenticada abre diretamente a tela antiga do usuario, preservando arvore, filtros e abas.
employees = '''{% extends "base.html" %}
{% block title %}Usuarios | Gestao de Acessos{% endblock %}
{% block content %}
<section class="hero compact"><p class="eyebrow">Escopo departamental</p><h1>Usuarios</h1><p>{% if user.department %}Somente funcionarios de {{ user.department.nome }}.{% else %}Todos os departamentos autorizados para T.I.{% endif %}</p></section>
<section class="people-grid">{% for employee in employees %}<a class="person-card" href="/funcionarios/{{ employee.id }}"><strong>{{ employee.nome }}</strong><span>{{ employee.login }}</span><small>{{ employee.departamento.nome if employee.departamento else 'Sem departamento' }}</small></a>{% else %}<article class="panel">Nenhum funcionario no seu escopo.</article>{% endfor %}</section>
{% endblock %}'''
(T/'portal_employees.html').write_text(employees, encoding='utf-8', newline='\n')

# 3. Perfis autenticados abrem diretamente a tela antiga, preservando arvore e filtros.
profiles = '''{% extends "base.html" %}
{% block title %}Perfis | Gestao de Acessos{% endblock %}
{% block content %}
<section class="hero compact"><p class="eyebrow">Perfis importados do ERP</p><h1>Perfis do departamento</h1><p>{% if user.department %}Perfis utilizados por funcionarios de {{ user.department.nome }}.{% else %}Todos os perfis disponiveis para T.I.{% endif %}</p></section>
<section class="people-grid">{% for p in profiles %}<a class="person-card" href="/perfis/{{ p.id }}"><strong>{{ p.nome }}</strong><span>{{ p.situacao }}</span><small>Importado do ERP</small></a>{% else %}<article class="panel">Nenhum perfil encontrado.</article>{% endfor %}</section>
{% endblock %}'''
(T/'portal_profiles.html').write_text(profiles, encoding='utf-8', newline='\n')

# 4. Middleware central: injeta usuario em telas antigas, exige login e valida departamento.
access = ACCESS.read_text(encoding='utf-8')
if 'async def integrated_access_middleware(' not in access:
    middleware = r'''

PUBLIC_PATHS = {'/login', '/health'}
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
            return RedirectResponse('/login', status_code=303)

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
'''
    # append before first router route; definitions may occur anywhere before main imports module.
    first_route = access.find('@router.')
    if first_route < 0:
        raise SystemExit('Nenhuma rota encontrada em app/access_control.py')
    access = access[:first_route] + middleware + '\n\n' + access[first_route:]
ACCESS.write_text(access, encoding='utf-8', newline='\n')

# 5. Registra middleware uma unica vez no app principal, depois de importar access_control.
main = MAIN.read_text(encoding='utf-8')
old = "from app.access_control import create_tables as create_access_tables, router as access_router\ncreate_access_tables()\napp.include_router(access_router)"
new = "from app.access_control import create_tables as create_access_tables, integrated_access_middleware, router as access_router\ncreate_access_tables()\napp.middleware('http')(integrated_access_middleware)\napp.include_router(access_router)"
if old in main:
    main = main.replace(old, new)
elif "app.middleware('http')(integrated_access_middleware)" not in main:
    raise SystemExit('Bloco de integracao do access_control nao encontrado em app/main.py')
MAIN.write_text(main, encoding='utf-8', newline='\n')

py_compile.compile(str(ACCESS), doraise=True)
py_compile.compile(str(MAIN), doraise=True)
print('Integracao corrigida sem substituir as telas antigas de usuario e perfil.')
print('- Sessao reconhecida em todas as telas')
print('- Telas antigas nao exibem mais o botao Entrar durante a navegacao')
print('- Clique em usuario abre novamente a arvore, filtros, perfis e consolidado anteriores')
print('- Clique em perfil abre novamente a arvore e filtros anteriores')
print('- Escopo departamental validado antes de abrir usuario ou perfil')
