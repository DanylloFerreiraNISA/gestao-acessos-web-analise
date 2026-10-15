from __future__ import annotations

import py_compile
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
ACCESS = ROOT / 'app' / 'access_control.py'
TEMPLATES = ROOT / 'app' / 'templates'
STYLES = ROOT / 'app' / 'static' / 'styles.css'
PORTAL = ROOT / 'app' / 'static' / 'portal.css'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
BACKUP = ROOT / f'backup_cadastro_departamento_transferencia_v3_{STAMP}'
MARK = 'CADASTRO_DEPARTAMENTO_TRANSFERENCIA_V3'

required = [ACCESS, STYLES, PORTAL, TEMPLATES / 'department_manage.html']
missing = [str(path) for path in required if not path.is_file()]
if missing:
    raise RuntimeError('Arquivos ausentes: ' + ', '.join(missing) + '. Execute primeiro a correcao V2 de departamentos.')

access = ACCESS.read_text(encoding='utf-8-sig')
styles = STYLES.read_text(encoding='utf-8-sig')
portal = PORTAL.read_text(encoding='utf-8-sig')
if MARK in access:
    print('[OK] A melhoria V3 ja esta instalada.')
    raise SystemExit(0)
if 'DEPARTAMENTOS_SEPARACAO_ARVORE_CADASTRO_V2' not in access:
    raise RuntimeError('A separacao V2 de departamentos nao foi localizada. Nenhum arquivo foi alterado.')

routes = r'''

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
    selected_cargo = session.get(Cargo, cargo_id) if cargo_id else (cargos[0] if cargos else None)
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
        f'/admin/cadastros/departamentos/{department_id}/painel?aba=cargos&cargo_id={cargo.id}',
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
'''
access = access.rstrip() + routes + '\n'

# Redireciona os botoes da lista administrativa para o novo painel V3.
departments_path = TEMPLATES / 'departments.html'
if departments_path.is_file():
    departments_html = departments_path.read_text(encoding='utf-8-sig')
    departments_html = departments_html.replace(
        '/admin/cadastros/departamentos/{{ item.id }}',
        '/admin/cadastros/departamentos/{{ item.id }}/painel',
    )
else:
    raise RuntimeError('departments.html nao foi encontrado.')

manage_html = '''{% extends "base.html" %}
{% block title %}{{ department.nome }} | Cadastro{% endblock %}
{% block content %}
<a class="back" href="/admin/departamentos">Voltar para departamentos</a>
<section class="hero compact"><p class="eyebrow">Cadastro de departamento</p><h1>{{ department.nome }}</h1><p>Informe os usuarios do departamento e gerencie cargos em abas separadas.</p></section>
<div class="department-admin-actions"><a class="secondary-button" href="/admin/cadastros/departamentos/{{ department.id }}/editar">Editar departamento</a></div>
<nav class="department-tabs"><a class="{{ 'active' if aba == 'usuarios' else '' }}" href="?aba=usuarios">Usuarios do departamento</a><a class="{{ 'active' if aba == 'cargos' else '' }}" href="?aba=cargos{% if selected_cargo %}&cargo_id={{ selected_cargo.id }}{% endif %}">Cargos</a></nav>
{% if aba == 'usuarios' %}
<section class="panel"><h2>Usuarios do departamento</h2><p>Selecione os usuarios que pertencem ao departamento. A remocao tambem retira cargos deste departamento.</p><form method="post" action="/admin/cadastros/departamentos/{{ department.id }}/usuarios" data-transfer-form><div class="transfer-grid"><section><label>Usuarios disponiveis</label><input type="search" placeholder="Pesquisar disponiveis" data-transfer-search="available"><select multiple size="16" data-transfer-list="available">{% for employee in available_employees %}<option value="{{ employee.id }}">{{ employee.nome }} ({{ employee.login }})</option>{% endfor %}</select></section><div class="transfer-actions"><button type="button" data-transfer="right">Adicionar →</button><button type="button" class="secondary" data-transfer="left">← Remover</button><button type="button" data-transfer="all-right">Adicionar todos</button><button type="button" class="secondary" data-transfer="all-left">Remover todos</button></div><section><label>Usuarios deste departamento</label><input type="search" placeholder="Pesquisar vinculados" data-transfer-search="selected"><select multiple size="16" name="employee_ids" data-transfer-list="selected">{% for employee in linked_employees %}<option value="{{ employee.id }}">{{ employee.nome }} ({{ employee.login }})</option>{% endfor %}</select></section></div><div class="form-actions"><button>Salvar usuarios do departamento</button></div></form></section>
{% else %}
<section class="department-cargo-layout"><aside class="panel cargo-sidebar"><div class="panel-title"><h2>Cargos</h2><a class="button small" href="?aba=cargos">Novo</a></div>{% for cargo in cargos %}<a class="cargo-nav-item {{ 'active' if selected_cargo and selected_cargo.id == cargo.id else '' }}" href="?aba=cargos&cargo_id={{ cargo.id }}"><strong>{{ cargo.nome }}</strong><small>{{ 'Ativo' if cargo.ativo else 'Inativo' }}</small></a>{% else %}<p>Nenhum cargo cadastrado.</p>{% endfor %}</aside><div>
<section class="panel"><h2>{{ 'Editar cargo' if selected_cargo else 'Novo cargo' }}</h2><form method="post" action="/admin/cadastros/departamentos/{{ department.id }}/cargos/v3" class="integrated-form">{% if selected_cargo %}<input type="hidden" name="cargo_id" value="{{ selected_cargo.id }}">{% endif %}<label>Nome<input name="nome" value="{{ selected_cargo.nome if selected_cargo else '' }}" required></label><label>Descricao<input name="descricao" value="{{ selected_cargo.descricao or '' if selected_cargo else '' }}"></label><label class="full">Observacoes<textarea name="observacao">{{ selected_cargo.observacao or '' if selected_cargo else '' }}</textarea></label>{% if selected_cargo %}<label class="checkbox-field full"><input type="checkbox" name="ativo" {% if selected_cargo.ativo %}checked{% endif %}> Cargo ativo</label>{% endif %}<div class="full form-actions"><button>{{ 'Salvar cargo' if selected_cargo else 'Criar cargo' }}</button></div></form></section>
{% if selected_cargo %}<section class="panel"><h2>Usuarios e sistemas de {{ selected_cargo.nome }}</h2><form method="post" action="/admin/cadastros/departamentos/{{ department.id }}/cargos/{{ selected_cargo.id }}/vinculos-v3" data-transfer-form><h3>Usuarios do cargo</h3><p>Somente usuarios previamente vinculados ao departamento aparecem aqui.</p><div class="transfer-grid"><section><label>Disponiveis no departamento</label><input type="search" placeholder="Pesquisar disponiveis" data-transfer-search="available"><select multiple size="13" data-transfer-list="available">{% for employee in cargo_available_users %}<option value="{{ employee.id }}">{{ employee.nome }}</option>{% endfor %}</select></section><div class="transfer-actions"><button type="button" data-transfer="right">Adicionar →</button><button type="button" class="secondary" data-transfer="left">← Remover</button><button type="button" data-transfer="all-right">Adicionar todos</button><button type="button" class="secondary" data-transfer="all-left">Remover todos</button></div><section><label>Usuarios vinculados ao cargo</label><input type="search" placeholder="Pesquisar vinculados" data-transfer-search="selected"><select multiple size="13" name="employee_ids" data-transfer-list="selected">{% for employee in cargo_users %}<option value="{{ employee.id }}">{{ employee.nome }}</option>{% endfor %}</select></section></div><h3>Sistemas do cargo</h3><div class="check-grid">{% for system in systems %}<label><input type="checkbox" name="system_ids" value="{{ system.id }}" {% if system.id in cargo_system_ids %}checked{% endif %}> {{ system.nome }}</label>{% else %}<span>Nenhum sistema cadastrado.</span>{% endfor %}</div><div class="form-actions"><button>Salvar usuarios e sistemas</button></div></form></section>{% endif %}
</div></section>
{% endif %}
{% endblock %}
{% block scripts %}<script src="/static/transfer-list.js"></script>{% endblock %}'''

transfer_js = '''document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('[data-transfer-form]').forEach(form=>{
    const available=form.querySelector('[data-transfer-list="available"]');
    const selected=form.querySelector('[data-transfer-list="selected"]');
    if(!available||!selected)return;
    const move=(from,to,all=false)=>{
      [...from.options].filter(option=>all||option.selected).forEach(option=>{option.selected=false;to.add(option)});
      sort(to);sort(from);
    };
    const sort=select=>[...select.options].sort((a,b)=>a.text.localeCompare(b.text,'pt-BR')).forEach(o=>select.add(o));
    form.querySelector('[data-transfer="right"]')?.addEventListener('click',()=>move(available,selected));
    form.querySelector('[data-transfer="left"]')?.addEventListener('click',()=>move(selected,available));
    form.querySelector('[data-transfer="all-right"]')?.addEventListener('click',()=>move(available,selected,true));
    form.querySelector('[data-transfer="all-left"]')?.addEventListener('click',()=>move(selected,available,true));
    form.querySelectorAll('[data-transfer-search]').forEach(input=>input.addEventListener('input',()=>{
      const list=form.querySelector(`[data-transfer-list="${input.dataset.transferSearch}"]`);
      const q=input.value.trim().toLocaleLowerCase('pt-BR');
      [...list.options].forEach(option=>option.hidden=!!q&&!option.text.toLocaleLowerCase('pt-BR').includes(q));
    }));
    form.addEventListener('submit',()=>[...selected.options].forEach(option=>option.selected=true));
  });
});'''

css = '''
/* CADASTRO_DEPARTAMENTO_TRANSFERENCIA_V3 */
.department-tabs{display:flex;gap:8px;margin:16px 0}.department-tabs a{padding:10px 15px;border-radius:8px;background:#e9eef4;color:#17365d;text-decoration:none;font-weight:700}.department-tabs a.active{background:#17365d;color:#fff}.transfer-grid{display:grid;grid-template-columns:minmax(260px,1fr) auto minmax(260px,1fr);gap:14px;align-items:center}.transfer-grid section{display:grid;gap:7px}.transfer-grid select{width:100%;min-height:330px;padding:7px;border:1px solid #aebdca;border-radius:8px;background:#fff}.transfer-grid input{padding:9px;border:1px solid #aebdca;border-radius:7px}.transfer-actions{display:grid;gap:8px}.department-cargo-layout{display:grid;grid-template-columns:minmax(230px,.35fr) minmax(520px,1fr);gap:16px}.cargo-sidebar{align-self:start}.cargo-nav-item{display:flex;justify-content:space-between;gap:8px;padding:11px;border-bottom:1px solid #e4e9ee;color:#172033;text-decoration:none}.cargo-nav-item.active{background:#dbeafe;color:#17365d}.cargo-nav-item small{color:#667085}@media(max-width:900px){.transfer-grid,.department-cargo-layout{grid-template-columns:1fr}.transfer-actions{grid-template-columns:1fr 1fr}.transfer-grid select{min-height:220px}}
'''
if MARK not in styles:
    styles = styles.rstrip() + '\n' + css
if MARK not in portal:
    portal = portal.rstrip() + '\n' + css

outputs = {
    ACCESS: access,
    departments_path: departments_html,
    TEMPLATES / 'department_manage_v3.html': manage_html,
    ROOT / 'app' / 'static' / 'transfer-list.js': transfer_js,
    STYLES: styles,
    PORTAL: portal,
}

with tempfile.NamedTemporaryFile('w', suffix='.py', encoding='utf-8', delete=False) as temp:
    temp.write(access)
    temp_name = temp.name
try:
    py_compile.compile(temp_name, doraise=True)
finally:
    Path(temp_name).unlink(missing_ok=True)

for expected in (MARK, 'departamento_usuarios_sync_v3', 'cargo_vinculos_sync_v3', 'department_manage_v3.html'):
    if expected not in access:
        raise RuntimeError(f'Validacao falhou: {expected}')

created=[]
for path in outputs:
    if path.exists():
        dest=BACKUP/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    else:
        created.append(path)
try:
    for path,content in outputs.items():
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    py_compile.compile(str(ACCESS),doraise=True)
except Exception:
    for path in outputs:
        saved=BACKUP/path.relative_to(ROOT)
        if saved.exists():shutil.copy2(saved,path)
    for path in created:path.unlink(missing_ok=True)
    raise

print('\n[SUCESSO] Cadastro de departamento V3 instalado.')
print('[OK] Aba Usuarios do departamento com transferencia entre duas listas.')
print('[OK] Aba Cargos com criacao e edicao.')
print('[OK] Dentro do cargo, transferencia mostra somente usuarios do departamento.')
print('[OK] Remover usuario do departamento limpa cargos daquele departamento.')
print('[OK] Sistemas permanecem configurados dentro do cargo.')
print(f'[BACKUP] {BACKUP}')
print('\nReinicie o servidor e use Ctrl+F5.')
