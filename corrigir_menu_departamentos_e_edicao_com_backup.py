from __future__ import annotations

import ast
import py_compile
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
ACCESS = ROOT / "app" / "access_control.py"
BASE = ROOT / "app" / "templates" / "base.html"
DEPARTMENTS = ROOT / "app" / "templates" / "departments.html"
DETAIL = ROOT / "app" / "templates" / "department_detail.html"
STYLES = ROOT / "app" / "static" / "styles.css"
PORTAL = ROOT / "app" / "static" / "portal.css"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_menu_departamentos_edicao_{STAMP}"
MARK = "MENU_DEPARTAMENTOS_E_EDICAO_V1"

required = [ACCESS, BASE, DEPARTMENTS, DETAIL, STYLES, PORTAL]
missing = [str(path) for path in required if not path.is_file()]
if missing:
    raise RuntimeError(
        "Arquivos ausentes: " + ", ".join(missing) +
        ". Execute primeiro o instalador do modulo Cadastros."
    )

access = ACCESS.read_text(encoding="utf-8-sig")
base = BASE.read_text(encoding="utf-8-sig")
styles = STYLES.read_text(encoding="utf-8-sig")
portal = PORTAL.read_text(encoding="utf-8-sig")

if MARK in access:
    print("[OK] A correcao de menu e edicao de departamentos ja esta instalada.")
    raise SystemExit(0)

if "MODULO_CADASTROS_ORGANIZACIONAIS_V1" not in access:
    raise RuntimeError("O modulo Cadastros nao foi localizado. Nenhum arquivo foi alterado.")

# Departamentos vira uma tela propria na barra superior. Cadastros continua
# responsavel pelo cadastro administrativo.
nav_anchor = '<a href="/admin/cadastros">Cadastros</a>'
if nav_anchor not in base:
    raise RuntimeError("O link Cadastros nao foi localizado em base.html.")
base = base.replace(
    nav_anchor,
    nav_anchor + '\n          <a href="/admin/departamentos">Departamentos</a>',
    1,
)

# Acrescenta rotas sem substituir as existentes.
route_block = r'''

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
'''
access = access.rstrip() + route_block + "\n"

# Lista administrativa com botoes separados para arvore e edicao.
departments_html = '''{% extends "base.html" %}
{% block title %}Departamentos{% endblock %}
{% block content %}
<a class="back" href="/admin/cadastros">Voltar para cadastros</a>
<section class="hero compact">
  <p class="eyebrow">Cadastros</p>
  <h1>Departamentos</h1>
  <p>Cadastre, edite e abra a arvore organizacional de cada departamento.</p>
</section>
<form method="post" class="panel inline-create">
  <label>Nome do departamento<input name="nome" required></label>
  <button>Criar departamento</button>
</form>
<section class="panel">
  <div class="responsive-table">
    <table>
      <thead><tr><th>Departamento</th><th>Situacao</th><th>Acoes</th></tr></thead>
      <tbody>
      {% for item in departments %}
        <tr>
          <td>{{ item.nome }}</td>
          <td>{{ 'Ativo' if item.ativo else 'Inativo' }}</td>
          <td class="table-actions">
            <a class="button small" href="/admin/departamentos/{{ item.id }}">Abrir arvore</a>
            <a class="secondary-button small" href="/admin/departamentos/{{ item.id }}/editar">Editar</a>
          </td>
        </tr>
      {% else %}
        <tr><td colspan="3">Nenhum departamento cadastrado.</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</section>
{% endblock %}
'''

# A arvore permanece em pagina propria, acessivel diretamente pelo menu.
detail = DETAIL.read_text(encoding="utf-8-sig")
hero_end = '</section>'
hero_pos = detail.find(hero_end)
if hero_pos < 0:
    raise RuntimeError("O cabecalho de department_detail.html nao foi reconhecido.")
edit_action = '<div class="department-page-actions"><a class="secondary-button" href="/admin/departamentos/{{ department.id }}/editar">Editar departamento</a></div>'
if "department-page-actions" not in detail:
    detail = detail[:hero_pos + len(hero_end)] + edit_action + detail[hero_pos + len(hero_end):]

edit_html = '''{% extends "base.html" %}
{% block title %}Editar departamento{% endblock %}
{% block content %}
<a class="back" href="/admin/departamentos/{{ department.id }}">Voltar para a arvore</a>
<section class="hero compact">
  <p class="eyebrow">Cadastros</p>
  <h1>Editar departamento</h1>
  <p>Altere o nome ou a situacao do departamento.</p>
</section>
<form method="post" class="panel integrated-form">
  {% if error %}<div class="alert error full">{{ error }}</div>{% endif %}
  <label>Nome<input name="nome" value="{{ department.nome }}" required></label>
  <label class="checkbox-field"><input type="checkbox" name="ativo" {% if department.ativo %}checked{% endif %}> Departamento ativo</label>
  <div class="full form-actions">
    <a class="secondary-button" href="/admin/departamentos/{{ department.id }}">Cancelar</a>
    <button>Salvar alteracoes</button>
  </div>
</form>
{% endblock %}
'''

css = '''
/* MENU_DEPARTAMENTOS_E_EDICAO_V1 */
.table-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.secondary-button.small{padding:6px 10px;font-size:13px}
.department-page-actions{display:flex;justify-content:flex-end;margin:0 0 12px}
@media(max-width:700px){.table-actions{align-items:stretch;flex-direction:column}.table-actions a{text-align:center}}
'''
if "MENU_DEPARTAMENTOS_E_EDICAO_V1" not in styles:
    styles = styles.rstrip() + "\n" + css
if "MENU_DEPARTAMENTOS_E_EDICAO_V1" not in portal:
    portal = portal.rstrip() + "\n" + css

outputs = {
    ACCESS: access,
    BASE: base,
    DEPARTMENTS: departments_html,
    DETAIL: detail,
    ROOT / "app" / "templates" / "department_edit.html": edit_html,
    STYLES: styles,
    PORTAL: portal,
}

# Valida Python antes de criar backup e gravar.
with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as temp:
    temp.write(access)
    temp_name = temp.name
try:
    py_compile.compile(temp_name, doraise=True)
finally:
    Path(temp_name).unlink(missing_ok=True)

for expected in (MARK, "/admin/departamentos/{department_id}/editar", "department_edit.html"):
    if expected not in access:
        raise RuntimeError(f"Validacao falhou: {expected}. Nenhum arquivo foi alterado.")

# Backup de todos os existentes; novos arquivos entram na lista de rollback.
created = []
for path in outputs:
    if path.exists():
        destination = BACKUP / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
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

print("\n[SUCESSO] Menu e edicao de departamentos corrigidos.")
print("[OK] Departamentos agora aparece na barra superior.")
print("[OK] A tela Departamentos continua permitindo novos cadastros.")
print("[OK] Cada departamento possui Abrir arvore e Editar.")
print("[OK] Nome e situacao do departamento podem ser alterados.")
print(f"[BACKUP] {BACKUP}")
print("\nReinicie o servidor e atualize o navegador com Ctrl+F5.")
