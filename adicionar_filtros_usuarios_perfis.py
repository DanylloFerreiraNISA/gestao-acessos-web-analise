from pathlib import Path
from datetime import datetime
import py_compile, shutil

ROOT=Path.cwd().resolve(); AC=ROOT/'app'/'access_control.py'; T=ROOT/'app'/'templates'; CSS=ROOT/'app'/'static'/'portal.css'
EMP=T/'portal_employees.html'; PRO=T/'portal_profiles.html'; files=[AC,EMP,PRO,CSS]
missing=[str(p) for p in files if not p.exists()]
if missing: raise SystemExit('ERRO: arquivos ausentes; nada alterado: '+', '.join(missing))
backup=ROOT/f"backup_filtros_usuarios_perfis_{datetime.now():%Y%m%d_%H%M%S}"
for p in files:
 d=backup/p.relative_to(ROOT); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,d)

def replace_route(code, decorator, replacement):
 start=code.find(decorator)
 if start<0: raise RuntimeError('Rota não encontrada: '+decorator)
 end=code.find('\n@router.',start+len(decorator))
 if end<0: end=len(code)
 return code[:start]+replacement.rstrip()+'\n\n'+code[end+1:]

try:
 code=AC.read_text(encoding='utf-8')
 employees_route='''@router.get('/portal/funcionarios', response_class=HTMLResponse)
def portal_employees(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
    nome: str = '',
    departamento_id: int | None = None,
):
    nome = nome.strip()
    ti_manager = user.role in {ROLE_ADMIN, ROLE_ANALYST}
    query = scoped_employee_query(user)
    if nome:
        query = query.where(Funcionario.nome.ilike(f'%{nome}%'))
    if ti_manager and departamento_id:
        query = query.where(Funcionario.departamento_id == departamento_id)
    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if ti_manager else []
    employees = session.scalars(query).all()
    return templates.TemplateResponse(
        request=request,
        name='portal_employees.html',
        context={
            'user': user,
            'employees': employees,
            'departments': departments,
            'filter_name': nome,
            'filter_department_id': departamento_id,
            'show_department_filter': ti_manager,
        },
    )'''
 profiles_route='''@router.get('/portal/perfis', response_class=HTMLResponse)
def portal_profiles(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
    nome: str = '',
    departamento_id: int | None = None,
):
    nome = nome.strip()
    ti_manager = user.role in {ROLE_ADMIN, ROLE_ANALYST}
    query = select(Perfil).order_by(Perfil.nome)
    if user.role == ROLE_MANAGER:
        query = query.where(Perfil.id.in_(profile_ids_for_department(session, user.department_id)))
    elif departamento_id:
        query = query.where(Perfil.id.in_(profile_ids_for_department(session, departamento_id)))
    if nome:
        query = query.where(Perfil.nome.ilike(f'%{nome}%'))
    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if ti_manager else []
    profiles = session.scalars(query).unique().all()
    return templates.TemplateResponse(
        request=request,
        name='portal_profiles.html',
        context={
            'user': user,
            'profiles': profiles,
            'departments': departments,
            'filter_name': nome,
            'filter_department_id': departamento_id,
            'show_department_filter': ti_manager,
        },
    )'''
 code=replace_route(code,"@router.get('/portal/funcionarios', response_class=HTMLResponse)",employees_route)
 code=replace_route(code,"@router.get('/portal/perfis', response_class=HTMLResponse)",profiles_route)
 AC.write_text(code,encoding='utf-8',newline='\n')

 EMP.write_text('''{% extends "base.html" %}
{% block title %}Usuários | Gestão de Acessos{% endblock %}
{% block content %}
<section class="hero compact"><p class="eyebrow">Escopo departamental</p><h1>Usuários</h1><p>{% if user.department %}Somente funcionários de {{ user.department.nome }}.{% else %}Todos os departamentos autorizados para T.I.{% endif %}</p></section>
<form method="get" class="directory-filters">
<label>Pesquisar por nome<input type="search" name="nome" value="{{ filter_name }}" placeholder="Digite o nome do usuário"></label>
{% if show_department_filter %}<label>Departamento<select name="departamento_id"><option value="">Todos os departamentos</option>{% for d in departments %}<option value="{{ d.id }}" {% if filter_department_id == d.id %}selected{% endif %}>{{ d.nome }}</option>{% endfor %}</select></label>{% endif %}
<div class="filter-actions"><button type="submit">Filtrar</button><a href="/portal/funcionarios">Limpar</a></div>
</form>
<p class="filter-result">{{ employees|length }} usuário(s) encontrado(s).</p>
<section class="people-grid">{% for employee in employees %}<a class="person-card" href="/funcionarios/{{ employee.id }}"><strong>{{ employee.nome }}</strong><span>{{ employee.login }}</span><small>{{ employee.departamento.nome if employee.departamento else 'Sem departamento' }}</small></a>{% else %}<article class="panel">Nenhum usuário encontrado com os filtros informados.</article>{% endfor %}</section>
{% endblock %}''',encoding='utf-8')

 PRO.write_text('''{% extends "base.html" %}
{% block title %}Perfis | Gestão de Acessos{% endblock %}
{% block content %}
<section class="hero compact"><p class="eyebrow">Perfis importados do ERP</p><h1>Perfis</h1><p>{% if user.department %}Perfis utilizados por funcionários de {{ user.department.nome }}.{% else %}Todos os perfis disponíveis para T.I.{% endif %}</p></section>
<form method="get" class="directory-filters">
<label>Pesquisar por nome<input type="search" name="nome" value="{{ filter_name }}" placeholder="Digite o nome do perfil"></label>
{% if show_department_filter %}<label>Departamento<select name="departamento_id"><option value="">Todos os departamentos</option>{% for d in departments %}<option value="{{ d.id }}" {% if filter_department_id == d.id %}selected{% endif %}>{{ d.nome }}</option>{% endfor %}</select></label>{% endif %}
<div class="filter-actions"><button type="submit">Filtrar</button><a href="/portal/perfis">Limpar</a></div>
</form>
<p class="filter-result">{{ profiles|length }} perfil(is) encontrado(s).</p>
<section class="people-grid">{% for p in profiles %}<a class="person-card" href="/perfis/{{ p.id }}"><strong>{{ p.nome }}</strong><span>{{ p.situacao }}</span><small>{% if filter_department_id %}Utilizado no departamento selecionado{% else %}Importado do ERP{% endif %}</small></a>{% else %}<article class="panel">Nenhum perfil encontrado com os filtros informados.</article>{% endfor %}</section>
{% endblock %}''',encoding='utf-8')

 css=CSS.read_text(encoding='utf-8')
 marker='/* DIRECTORY_FILTERS_V1 */'
 if marker not in css:
  css+='''\n/* DIRECTORY_FILTERS_V1 */\n.directory-filters{display:grid;grid-template-columns:minmax(260px,1fr) minmax(230px,.65fr) auto;gap:12px;align-items:end;background:#fff;border:1px solid #d7e0e8;border-radius:10px;padding:16px;margin:18px 0 8px}.directory-filters label{display:grid;gap:6px;font-weight:700}.directory-filters input,.directory-filters select{width:100%;padding:10px;border:1px solid #aebdca;border-radius:7px;background:#fff}.filter-actions{display:flex;gap:9px;align-items:center}.filter-actions a{padding:9px 12px}.filter-result{color:#65758b;margin:10px 0 16px}@media(max-width:800px){.directory-filters{grid-template-columns:1fr}}\n'''
  CSS.write_text(css,encoding='utf-8',newline='\n')
 py_compile.compile(str(AC),doraise=True)
except Exception as exc:
 for p in files: shutil.copy2(backup/p.relative_to(ROOT),p)
 raise SystemExit(f'ERRO: alteração cancelada e arquivos restaurados: {exc}')

print('Filtros adicionados com sucesso.')
print('- Usuários: pesquisa por nome para todos; departamento apenas para T.I.')
print('- Perfis: pesquisa por nome para todos; departamento apenas para T.I.')
print('- Gestores de departamento continuam limitados ao próprio departamento.')
print('Backup:',backup)
