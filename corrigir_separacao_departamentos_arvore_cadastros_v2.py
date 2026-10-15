from __future__ import annotations

import ast
import py_compile
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
ACCESS = ROOT / "app" / "access_control.py"
BASE = ROOT / "app" / "templates" / "base.html"
STYLES = ROOT / "app" / "static" / "styles.css"
PORTAL = ROOT / "app" / "static" / "portal.css"
TEMPLATES = ROOT / "app" / "templates"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_departamentos_separacao_v2_{STAMP}"
MARK = "DEPARTAMENTOS_SEPARACAO_ARVORE_CADASTRO_V2"

required = [ACCESS, BASE, STYLES, PORTAL]
missing = [str(p) for p in required if not p.is_file()]
if missing:
    raise RuntimeError("Arquivos ausentes: " + ", ".join(missing))

access = ACCESS.read_text(encoding="utf-8-sig")
base = BASE.read_text(encoding="utf-8-sig")
styles = STYLES.read_text(encoding="utf-8-sig")
portal = PORTAL.read_text(encoding="utf-8-sig")

if MARK in access:
    print("[OK] A separacao V2 ja esta instalada.")
    raise SystemExit(0)
if "MODULO_CADASTROS_ORGANIZACIONAIS_V1" not in access:
    raise RuntimeError("O modulo Cadastros nao foi encontrado. Nenhum arquivo foi alterado.")

# O menu Departamentos passa a apontar para uma visualizacao exclusiva da arvore.
if '<a href="/admin/departamentos">Departamentos</a>' in base:
    base = base.replace(
        '<a href="/admin/departamentos">Departamentos</a>',
        '<a href="/portal/departamentos">Departamentos</a>',
        1,
    )
elif '<a href="/portal/departamentos">Departamentos</a>' not in base:
    anchor = '<a href="/admin/cadastros">Cadastros</a>'
    if anchor not in base:
        raise RuntimeError("Os links Cadastros/Departamentos nao foram reconhecidos em base.html.")
    base = base.replace(anchor, anchor + '\n          <a href="/portal/departamentos">Departamentos</a>', 1)

# Em vez de brigar com rotas antigas, cria um bloco V2 com caminhos novos e inequivocos.
route_block = r'''

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
'''
access = access.rstrip() + route_block + "\n"

# A tela administrativa lista departamentos e abre a manutencao, nunca a arvore.
departments_html = '''{% extends "base.html" %}
{% block title %}Cadastro de departamentos{% endblock %}
{% block content %}
<a class="back" href="/admin/cadastros">Voltar para cadastros</a>
<section class="hero compact"><p class="eyebrow">Cadastros</p><h1>Cadastro de departamentos</h1><p>Crie departamentos e abra a manutencao de cargos, sistemas e funcionarios.</p></section>
<form method="post" action="/admin/departamentos" class="panel inline-create"><label>Nome do departamento<input name="nome" required></label><button>Criar departamento</button></form>
<section class="panel"><div class="responsive-table"><table><thead><tr><th>Departamento</th><th>Situacao</th><th>Acoes</th></tr></thead><tbody>
{% for item in departments %}<tr><td>{{ item.nome }}</td><td>{{ 'Ativo' if item.ativo else 'Inativo' }}</td><td class="table-actions"><a class="button small" href="/admin/cadastros/departamentos/{{ item.id }}">Gerenciar</a><a class="secondary-button small" href="/admin/cadastros/departamentos/{{ item.id }}/editar">Editar</a></td></tr>
{% else %}<tr><td colspan="3">Nenhum departamento cadastrado.</td></tr>{% endfor %}
</tbody></table></div></section>
{% endblock %}'''

# Tela exclusiva da arvore, sem formulario administrativo.
tree_html = '''{% extends "base.html" %}
{% block title %}Departamentos{% endblock %}
{% block content %}
<section class="hero compact"><p class="eyebrow">Estrutura organizacional</p><h1>Departamentos</h1><p>Visualize cargos, sistemas, observacoes e os nomes dos usuarios vinculados.</p></section>
<section class="panel"><div class="tree-panel-heading"><h2>Arvore organizacional</h2><div class="tree-expand-controls"><button type="button" data-org-expand>Expandir tudo</button><button type="button" class="secondary" data-org-collapse>Recolher tudo</button></div></div><input class="classic-search" type="search" placeholder="Pesquisar departamento, cargo, sistema ou usuario" data-org-search>
<div class="org-tree" data-org-tree>
{% for department in departments %}<details class="org-department" data-search="{{ (department.nome ~ ' ' ~ cargos_by_department[department.id]|map(attribute='nome')|join(' '))|lower }}"><summary>🏢 {{ department.nome }}</summary><div class="org-children">
{% for cargo in cargos_by_department[department.id] %}<details class="org-cargo"><summary>📁 {{ cargo.nome }}</summary><div class="org-children"><details><summary>Sistemas ({{ systems_by_cargo[cargo.id]|length }})</summary><ul>{% for system in systems_by_cargo[cargo.id] %}<li>{{ system.nome }}</li>{% else %}<li>Nenhum sistema vinculado.</li>{% endfor %}</ul></details><details><summary>Observacoes</summary><p>{{ cargo.observacao or 'Nenhuma observacao.' }}</p></details><details><summary>Usuarios ({{ users_by_cargo[cargo.id]|length }})</summary><ul>{% for employee in users_by_cargo[cargo.id] %}<li>{{ employee.nome }}</li>{% else %}<li>Nenhum usuario vinculado.</li>{% endfor %}</ul></details></div></details>
{% else %}<p>Nenhum cargo cadastrado.</p>{% endfor %}</div></details>{% else %}<p>Nenhum departamento disponivel.</p>{% endfor %}
</div></section>
{% endblock %}
{% block scripts %}<script>document.addEventListener('DOMContentLoaded',()=>{const tree=document.querySelector('[data-org-tree]');if(!tree)return;const all=()=>tree.querySelectorAll('details');all().forEach(x=>x.open=false);document.querySelector('[data-org-expand]')?.addEventListener('click',()=>all().forEach(x=>x.open=true));document.querySelector('[data-org-collapse]')?.addEventListener('click',()=>all().forEach(x=>x.open=false));document.querySelector('[data-org-search]')?.addEventListener('input',e=>{const q=e.target.value.trim().toLowerCase();tree.querySelectorAll('.org-department').forEach(x=>{const visible=!q||x.textContent.toLowerCase().includes(q);x.hidden=!visible;if(q&&visible)x.open=true})})});</script>{% endblock %}'''

manage_html = '''{% extends "base.html" %}
{% block title %}Gerenciar {{ department.nome }}{% endblock %}
{% block content %}
<a class="back" href="/admin/departamentos">Voltar para o cadastro de departamentos</a>
<section class="hero compact"><p class="eyebrow">Cadastro de departamento</p><h1>{{ department.nome }}</h1><p>Gerencie cargos, sistemas e vinculos de funcionarios. A arvore fica na tela Departamentos do menu.</p></section>
<div class="department-admin-actions"><a class="secondary-button" href="/admin/cadastros/departamentos/{{ department.id }}/editar">Editar departamento</a></div>
<section class="panel"><h2>Novo cargo</h2><form method="post" action="/admin/cadastros/departamentos/{{ department.id }}/cargos" class="integrated-form"><label>Nome<input name="nome" required></label><label>Descricao<input name="descricao"></label><label class="full">Observacoes<textarea name="observacao"></textarea></label><button class="full">Criar cargo</button></form></section>
<section class="panel"><h2>Cargos e sistemas</h2><div class="cargo-admin-grid">{% for cargo in cargos %}<article class="cargo-admin-card"><h3>{{ cargo.nome }}</h3><p>{{ cargo.descricao or 'Sem descricao.' }}</p><p><strong>Observacoes:</strong> {{ cargo.observacao or 'Nenhuma.' }}</p><form method="post" action="/admin/cadastros/cargos/{{ cargo.id }}/sistemas"><div class="check-grid">{% for system in systems %}<label><input type="checkbox" name="system_ids" value="{{ system.id }}" {% if system.id in systems_by_cargo[cargo.id] %}checked{% endif %}> {{ system.nome }}</label>{% else %}<span>Nenhum sistema cadastrado.</span>{% endfor %}</div><button>Salvar sistemas</button></form></article>{% else %}<p>Nenhum cargo cadastrado.</p>{% endfor %}</div></section>
<section class="panel" id="funcionarios"><h2>Funcionarios do departamento</h2><p>Defina ou remova o cargo de cada funcionario individualmente.</p><div class="employee-assignment-list">{% for employee in employees %}<form method="post" action="/admin/cadastros/departamentos/{{ department.id }}/funcionarios/{{ employee.id }}/cargo" class="employee-assignment-row"><strong>{{ employee.nome }}</strong><span>{{ employee.login }}</span><select name="cargo_id"><option value="">Sem cargo</option>{% for cargo in cargos %}<option value="{{ cargo.id }}" {% if cargo.id in assignments[employee.id] %}selected{% endif %}>{{ cargo.nome }}</option>{% endfor %}</select><button>Salvar</button></form>{% else %}<p>Nenhum funcionario pertence a este departamento.</p>{% endfor %}</div></section>
{% endblock %}'''

edit_html = '''{% extends "base.html" %}{% block title %}Editar departamento{% endblock %}{% block content %}<a class="back" href="/admin/cadastros/departamentos/{{ department.id }}">Voltar para manutencao</a><section class="hero compact"><p class="eyebrow">Cadastros</p><h1>Editar departamento</h1></section><form method="post" class="panel integrated-form">{% if error %}<div class="alert error full">{{ error }}</div>{% endif %}<label>Nome<input name="nome" value="{{ department.nome }}" required></label><label class="checkbox-field"><input type="checkbox" name="ativo" {% if department.ativo %}checked{% endif %}> Departamento ativo</label><div class="full form-actions"><a class="secondary-button" href="/admin/cadastros/departamentos/{{ department.id }}">Cancelar</a><button>Salvar alteracoes</button></div></form>{% endblock %}'''

css = '''
/* DEPARTAMENTOS_SEPARACAO_ARVORE_CADASTRO_V2 */
.org-department,.org-cargo{border:1px solid #d7e1eb;border-radius:9px;margin:8px 0;background:#fbfcfe}.org-department>summary,.org-cargo>summary,.org-children details>summary{cursor:pointer;padding:10px;font-weight:700}.org-children{padding:0 14px 12px 28px}.department-admin-actions{display:flex;justify-content:flex-end;margin-bottom:12px}.cargo-admin-grid{display:grid;grid-template-columns:repeat(2,minmax(300px,1fr));gap:14px}.cargo-admin-card{border:1px solid #d7e1eb;border-radius:10px;padding:15px;background:#fbfcfe}.cargo-admin-card h3{margin-top:0}.check-grid{display:grid;grid-template-columns:repeat(2,minmax(150px,1fr));gap:7px;margin:12px 0}.employee-assignment-list{display:grid;gap:8px}.employee-assignment-row{display:grid;grid-template-columns:minmax(220px,1fr) minmax(160px,.7fr) minmax(220px,.8fr) auto;gap:10px;align-items:center;padding:10px;border:1px solid #e1e7ed;border-radius:8px}.employee-assignment-row span{color:#667085}@media(max-width:900px){.cargo-admin-grid{grid-template-columns:1fr}.employee-assignment-row{grid-template-columns:1fr}.check-grid{grid-template-columns:1fr}}
'''
if MARK not in styles:
    styles = styles.rstrip() + "\n" + css
if MARK not in portal:
    portal = portal.rstrip() + "\n" + css

outputs = {
    ACCESS: access,
    BASE: base,
    TEMPLATES / "departments.html": departments_html,
    TEMPLATES / "departments_tree.html": tree_html,
    TEMPLATES / "department_manage.html": manage_html,
    TEMPLATES / "department_edit_v2.html": edit_html,
    STYLES: styles,
    PORTAL: portal,
}

# Preflight Python validation.
with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as temp:
    temp.write(access)
    temp_name = temp.name
try:
    py_compile.compile(temp_name, doraise=True)
finally:
    Path(temp_name).unlink(missing_ok=True)

for expected in (MARK, "/portal/departamentos", "/admin/cadastros/departamentos/{department_id}", "funcionario_cargo_salvar_v2"):
    if expected not in access:
        raise RuntimeError(f"Validacao falhou: {expected}")

created = []
for path in outputs:
    if path.exists():
        dest = BACKUP / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    else:
        created.append(path)

try:
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    py_compile.compile(str(ACCESS), doraise=True)
except Exception:
    for path in outputs:
        saved = BACKUP / path.relative_to(ROOT)
        if saved.exists():
            shutil.copy2(saved, path)
    for path in created:
        path.unlink(missing_ok=True)
    raise

print("\n[SUCESSO] Departamentos separados corretamente.")
print("[OK] Menu Departamentos abre somente a arvore organizacional.")
print("[OK] Cadastros > Departamentos abre somente a manutencao.")
print("[OK] Edicao usa rotas V2 sem conflito e sem 404.")
print("[OK] Vinculo de funcionario foi substituido por uma linha individual com seletor de cargo.")
print("[OK] Para desvincular, selecione Sem cargo e salve.")
print(f"[BACKUP] {BACKUP}")
print("\nReinicie o servidor e use Ctrl+F5 no navegador.")
