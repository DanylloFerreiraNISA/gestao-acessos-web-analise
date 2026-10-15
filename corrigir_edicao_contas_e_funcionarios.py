from pathlib import Path
import py_compile

ROOT = Path.cwd()
APP = ROOT / 'app'
ACCESS = APP / 'access_control.py'
TEMPLATES = APP / 'templates'
STATIC = APP / 'static'

required = [ACCESS, TEMPLATES / 'login.html', TEMPLATES / 'base.html']
for path in required:
    if not path.exists():
        raise SystemExit(f'Arquivo obrigatorio nao encontrado: {path}')

text = ACCESS.read_text(encoding='utf-8')

# Garante funcao de normalizacao do username.
anchor = 'def hash_password(password: str) -> str:'
if 'def normalize_username(' not in text:
    helper = '''def normalize_username(value: str) -> str:\n    username = value.strip().lower()\n    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")\n    if not username or any(char not in allowed for char in username):\n        raise HTTPException(400, "Usuario invalido. Use letras, numeros, ponto, hifen ou sublinhado.")\n    return username\n\n\n'''
    if anchor not in text:
        raise SystemExit('Nao foi possivel localizar hash_password em app/access_control.py.')
    text = text.replace(anchor, helper + anchor, 1)

# Garante username no modelo de contas.
email_field = '    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)\n'
if 'username: Mapped[' not in text:
    if email_field not in text:
        raise SystemExit('Campo email de SystemUser nao localizado.')
    text = text.replace(
        email_field,
        email_field + '    username: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)\n',
        1,
    )

# Rotas de edicao de conta do sistema.
if "@router.get('/admin/contas/{account_id}/editar'" not in text:
    account_routes = r'''

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
'''
    marker = "@router.get('/portal'"
    pos = text.find(marker)
    if pos < 0:
        # fallback: inserir antes do include/router final ou no fim
        pos = len(text)
    text = text[:pos] + account_routes + '\n\n' + text[pos:]

# Rotas de edicao de funcionario, se ausentes.
if "@router.get('/portal/funcionarios/{employee_id}/editar'" not in text:
    employee_routes = r'''

@router.get('/portal/funcionarios/{employee_id}/editar', response_class=HTMLResponse)
def employee_edit_page(
    request: Request,
    employee_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
):
    employee = session.scalar(
        select(Funcionario)
        .options(selectinload(Funcionario.departamento))
        .where(Funcionario.id == employee_id)
    )
    if not employee:
        raise HTTPException(404, 'Funcionario nao encontrado')
    enforce_department(user, employee.departamento_id)
    departments = (
        session.scalars(select(Departamento).order_by(Departamento.nome)).all()
        if user.role in {ROLE_ADMIN, ROLE_ANALYST}
        else [employee.departamento]
    )
    return templates.TemplateResponse(
        request=request,
        name='employee_edit.html',
        context={
            'current_user': user,
            'user': user,
            'employee': employee,
            'departments': departments,
            'error': None,
        },
    )


@router.post('/portal/funcionarios/{employee_id}/editar', response_class=HTMLResponse)
def employee_edit_save(
    request: Request,
    employee_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
    name: Annotated[str, Form()],
    login: Annotated[str, Form()],
    department_id: Annotated[int, Form()],
    active: Annotated[str | None, Form()] = None,
):
    employee = session.scalar(
        select(Funcionario)
        .options(selectinload(Funcionario.departamento))
        .where(Funcionario.id == employee_id)
    )
    if not employee:
        raise HTTPException(404, 'Funcionario nao encontrado')
    enforce_department(user, employee.departamento_id)

    normalized_name = name.strip()
    normalized_login = login.strip().lower()
    if user.role == ROLE_MANAGER:
        department_id = user.department_id

    error = None
    if not normalized_name or not normalized_login or any(char.isspace() for char in normalized_login):
        error = 'Nome ou login invalido.'
    elif session.scalar(select(Funcionario).where(func.lower(Funcionario.login) == normalized_login, Funcionario.id != employee.id)):
        error = 'Ja existe outro funcionario com este login.'
    elif not session.get(Departamento, department_id):
        error = 'Departamento invalido.'

    if error:
        departments = (
            session.scalars(select(Departamento).order_by(Departamento.nome)).all()
            if user.role in {ROLE_ADMIN, ROLE_ANALYST}
            else [employee.departamento]
        )
        return templates.TemplateResponse(
            request=request,
            name='employee_edit.html',
            context={
                'current_user': user,
                'user': user,
                'employee': employee,
                'departments': departments,
                'error': error,
            },
            status_code=400,
        )

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
        pos = len(text)
    text = text[:pos] + employee_routes + '\n\n' + text[pos:]

ACCESS.write_text(text, encoding='utf-8', newline='\n')

# Tela de login sem nome pessoal no exemplo.
login_path = TEMPLATES / 'login.html'
login_html = login_path.read_text(encoding='utf-8')
login_html = login_html.replace('danyllo.ferreira', 'usuario.exemplo')
login_html = login_html.replace('nome@empresa.com ou usuario.exemplo', 'usuario.exemplo ou usuario@empresa.com')
login_path.write_text(login_html, encoding='utf-8', newline='\n')

# Tela de contas completa, com criação e edição.
accounts_html = '''{% extends "base.html" %}
{% block title %}Contas do sistema{% endblock %}
{% block content %}
<section class="hero compact">
  <p class="eyebrow">Administracao</p>
  <h1>Contas do sistema</h1>
  <p>Crie contas com e-mail e nome de usuario independentes.</p>
</section>
<form class="panel integrated-form account-create-form" method="post">
  {% if error %}<div class="alert error full">{{ error }}</div>{% endif %}
  <label>Nome<input name="name" placeholder="Nome da conta" required></label>
  <label>Usuario<input name="username" placeholder="usuario.exemplo" pattern="[A-Za-z0-9._-]+" required></label>
  <label>E-mail<input name="email" type="email" placeholder="usuario@empresa.com" required></label>
  <label>Senha inicial<input name="password" type="password" minlength="10" required></label>
  <label>Papel<select name="role" required><option value="GESTOR_DEPARTAMENTO">Gestor de departamento</option><option value="ANALISTA_TI">Analista T.I.</option><option value="ADMIN_TI">Admin T.I.</option></select></label>
  <label>Departamento<select name="department_id"><option value="">Sem departamento</option>{% for department in departments %}<option value="{{ department.id }}">{{ department.nome }}</option>{% endfor %}</select></label>
  <div class="full form-actions"><button class="primary">Criar conta</button></div>
</form>
<section class="panel">
  <div class="section-heading"><div><p class="eyebrow">Cadastradas</p><h2>Contas existentes</h2></div></div>
  <div class="responsive-table"><table><thead><tr><th>Nome</th><th>Usuario</th><th>E-mail</th><th>Papel</th><th>Departamento</th><th>Situacao</th><th></th></tr></thead><tbody>{% for account in accounts %}<tr><td>{{ account.name }}</td><td>@{{ account.username or '-' }}</td><td>{{ account.email }}</td><td>{{ account.role }}</td><td>{{ account.department.nome if account.department else '-' }}</td><td>{{ 'Ativa' if account.active else 'Inativa' }}</td><td><a class="button small" href="/admin/contas/{{ account.id }}/editar">Editar</a></td></tr>{% else %}<tr><td colspan="7">Nenhuma conta cadastrada.</td></tr>{% endfor %}</tbody></table></div>
</section>
{% endblock %}
'''
(TEMPLATES / 'accounts.html').write_text(accounts_html, encoding='utf-8', newline='\n')

# Edição de conta.
account_edit_html = '''{% extends "base.html" %}
{% block title %}Editar conta{% endblock %}
{% block content %}
<a class="back" href="/admin/contas">Voltar para contas</a>
<section class="hero compact"><p class="eyebrow">Administracao</p><h1>Editar conta</h1><p>Altere e-mail, usuario, papel, departamento, situacao ou senha.</p></section>
<form class="panel integrated-form" method="post">
  {% if error %}<div class="alert error full">{{ error }}</div>{% endif %}
  <label>Nome<input name="name" value="{{ account.name }}" required></label>
  <label>Usuario<input name="username" value="{{ account.username or '' }}" placeholder="usuario.exemplo" pattern="[A-Za-z0-9._-]+" required></label>
  <label>E-mail<input name="email" type="email" value="{{ account.email }}" required></label>
  <label>Papel<select name="role" required><option value="GESTOR_DEPARTAMENTO" {% if account.role == 'GESTOR_DEPARTAMENTO' %}selected{% endif %}>Gestor de departamento</option><option value="ANALISTA_TI" {% if account.role == 'ANALISTA_TI' %}selected{% endif %}>Analista T.I.</option><option value="ADMIN_TI" {% if account.role == 'ADMIN_TI' %}selected{% endif %}>Admin T.I.</option></select></label>
  <label>Departamento<select name="department_id"><option value="">Sem departamento</option>{% for department in departments %}<option value="{{ department.id }}" {% if account.department_id == department.id %}selected{% endif %}>{{ department.nome }}</option>{% endfor %}</select></label>
  <label>Nova senha <small>deixe vazio para manter</small><input name="new_password" type="password" minlength="10"></label>
  <label class="checkbox-field"><input type="checkbox" name="active" {% if account.active %}checked{% endif %}> Conta ativa</label>
  <div class="full form-actions"><a class="secondary-button" href="/admin/contas">Cancelar</a><button class="primary">Salvar alteracoes</button></div>
</form>
{% endblock %}
'''
(TEMPLATES / 'account_edit.html').write_text(account_edit_html, encoding='utf-8', newline='\n')

# Edição de funcionário.
employee_edit_html = '''{% extends "base.html" %}
{% block title %}Editar funcionario{% endblock %}
{% block content %}
<a class="back" href="/funcionarios/{{ employee.id }}">Voltar para o usuario</a>
<section class="hero compact"><p class="eyebrow">Cadastro</p><h1>Editar funcionario</h1><p>{% if user.role == 'GESTOR_DEPARTAMENTO' %}Edicao restrita ao seu departamento.{% else %}Edicao administrativa do cadastro importado.{% endif %}</p></section>
<form class="panel integrated-form" method="post">
  {% if error %}<div class="alert error full">{{ error }}</div>{% endif %}
  <label>Nome<input name="name" value="{{ employee.nome }}" required></label>
  <label>Login no sistema de origem<input name="login" value="{{ employee.login }}" required></label>
  <label>Departamento<select name="department_id" required {% if user.role == 'GESTOR_DEPARTAMENTO' %}disabled{% endif %}>{% for department in departments %}<option value="{{ department.id }}" {% if employee.departamento_id == department.id %}selected{% endif %}>{{ department.nome }}</option>{% endfor %}</select>{% if user.role == 'GESTOR_DEPARTAMENTO' %}<input type="hidden" name="department_id" value="{{ employee.departamento_id }}">{% endif %}</label>
  <label class="checkbox-field"><input type="checkbox" name="active" {% if employee.ativo %}checked{% endif %}> Funcionario ativo</label>
  <div class="full form-actions"><a class="secondary-button" href="/funcionarios/{{ employee.id }}">Cancelar</a><button class="primary">Salvar alteracoes</button></div>
</form>
{% endblock %}
'''
(TEMPLATES / 'employee_edit.html').write_text(employee_edit_html, encoding='utf-8', newline='\n')

# Adiciona o botão ao detalhe sem trocar a tela aprovada.
funcionario_path = TEMPLATES / 'funcionario.html'
if funcionario_path.exists():
    html = funcionario_path.read_text(encoding='utf-8')
    if '/portal/funcionarios/{{ funcionario.id }}/editar' not in html:
        button = '<div class="employee-page-actions"><a class="button" href="/portal/funcionarios/{{ funcionario.id }}/editar">Editar funcionario</a></div>'
        close = html.find('</section>')
        if close >= 0:
            close += len('</section>')
            html = html[:close] + button + html[close:]
        else:
            html = button + html
        funcionario_path.write_text(html, encoding='utf-8', newline='\n')

# CSS.
styles = STATIC / 'styles.css'
css = styles.read_text(encoding='utf-8') if styles.exists() else ''
if '/* ACCOUNT_EMPLOYEE_EDITOR */' not in css:
    css += '''\n/* ACCOUNT_EMPLOYEE_EDITOR */\n.responsive-table{overflow:auto}.responsive-table table{width:100%;border-collapse:collapse}.responsive-table th,.responsive-table td{padding:10px;border-bottom:1px solid #e5e7eb;text-align:left}.button.small{padding:6px 10px;font-size:13px}.employee-page-actions{display:flex;justify-content:flex-end;margin:-6px 0 12px}.checkbox-field{display:flex!important;align-items:center;gap:8px}.form-actions{display:flex;justify-content:flex-end;gap:8px}.secondary-button{padding:9px 13px;border-radius:7px;background:#e7edf3;color:#17365d;text-decoration:none}\n'''
styles.write_text(css, encoding='utf-8', newline='\n')

# Migração idempotente para username.
migration = '''from sqlalchemy import inspect, select, text\nfrom sqlalchemy.orm import Session\nfrom app.database import engine\nfrom app.access_control import SystemUser\n\nwith engine.begin() as connection:\n    columns = {item["name"] for item in inspect(connection).get_columns("system_users")}\n    if "username" not in columns:\n        connection.execute(text("ALTER TABLE system_users ADD COLUMN username VARCHAR(120)"))\n    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_system_users_username ON system_users (username)"))\n\nwith Session(engine) as session:\n    users = session.scalars(select(SystemUser).order_by(SystemUser.id)).all()\n    used = {item.username.lower() for item in users if item.username}\n    for item in users:\n        if item.username:\n            continue\n        base = "".join(char for char in item.email.split("@", 1)[0].lower() if char in "abcdefghijklmnopqrstuvwxyz0123456789._-") or f"usuario{item.id}"\n        candidate = base\n        number = 2\n        while candidate in used:\n            candidate = f"{base}.{number}"\n            number += 1\n        item.username = candidate\n        used.add(candidate)\n        print(f"{item.email} -> {candidate}")\n    session.commit()\nprint("Migracao de username concluida.")\n'''
(ROOT / 'migrar_username_contas.py').write_text(migration, encoding='utf-8', newline='\n')

py_compile.compile(str(ACCESS), doraise=True)
print('Edicao de contas e funcionarios instalada.')
print('- Exemplos pessoais removidos')
print('- Contas existentes agora podem ser editadas')
print('- Usuario e e-mail podem ser alterados independentemente')
print('- Nova senha e ativacao da conta disponiveis')
print('- Funcionarios existentes podem ser editados')
print('Execute agora: python .\\migrar_username_contas.py')
