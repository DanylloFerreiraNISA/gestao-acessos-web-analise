from pathlib import Path
import py_compile

root = Path.cwd()
access = root / 'app' / 'access_control.py'
template = root / 'app' / 'templates' / 'accounts.html'

for path in (access, template):
    if not path.exists():
        raise SystemExit(f'Arquivo nao encontrado: {path}')

# O template aceita os nomes de contexto usados pelas versoes anteriores.
html = template.read_text(encoding='utf-8')

if '{% set account_list =' not in html:
    marker = '{% block content %}'
    fallback = "{% set account_list = accounts if accounts is defined else (users if users is defined else (system_users if system_users is defined else [])) %}"
    if marker not in html:
        raise SystemExit('Bloco content nao encontrado em accounts.html')
    html = html.replace(marker, marker + '\n' + fallback, 1)

html = html.replace('{% for account in accounts %}', '{% for account in account_list %}')
template.write_text(html, encoding='utf-8', newline='\n')

# Ajusta a rota /admin/contas para sempre carregar os registros existentes.
text = access.read_text(encoding='utf-8')
route_marker = "@router.get('/admin/contas'"
start = text.find(route_marker)
if start < 0:
    raise SystemExit('Rota GET /admin/contas nao encontrada em access_control.py')

next_route = text.find('\n@router.', start + 1)
if next_route < 0:
    next_route = len(text)
block = text[start:next_route]

# Detecta o nome da funcao e substitui somente a rota GET de listagem.
func_at = block.find('\ndef ')
if func_at < 0:
    raise SystemExit('Funcao da rota /admin/contas nao encontrada')
func_line_end = block.find('\n', func_at + 1)
signature = block[func_at + 1:func_line_end]
func_name = signature.split('def ', 1)[1].split('(', 1)[0].strip()

new_block = f'''@router.get('/admin/contas', response_class=HTMLResponse)
def {func_name}(
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
        context={{
            'current_user': user,
            'user': user,
            'accounts': accounts,
            'users': accounts,
            'system_users': accounts,
            'departments': departments,
            'error': None,
        }},
    )
'''

text = text[:start] + new_block + text[next_route:]
access.write_text(text, encoding='utf-8', newline='\n')
py_compile.compile(str(access), doraise=True)

print('Lista de contas existentes restaurada.')
print('- A rota /admin/contas volta a consultar SystemUser no banco')
print('- O template aceita accounts, users ou system_users')
print('- Nenhuma conta foi excluida ou recriada')
