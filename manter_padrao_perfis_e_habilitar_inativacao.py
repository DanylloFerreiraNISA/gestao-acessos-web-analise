from __future__ import annotations

import py_compile
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
APP = ROOT / "app"
BACKEND = APP / "access_control.py"
TEMPLATES = APP / "templates"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_perfis_padrao_{STAMP}"
MARK = "PERFIS_PROPOSTA_PADRAO_V1"

if not BACKEND.exists():
    raise RuntimeError(f"Arquivo nao encontrado: {BACKEND}")


def route_block(text: str, route: str, method: str = "get"):
    pattern = re.compile(
        rf"(?ms)^@router\.{method}\([^\n]*{re.escape(route)}[^\n]*\)\s*\n"
        rf"def\s+\w+\(.*?(?=^@router\.|\Z)"
    )
    return pattern.search(text)


def backup(path: Path):
    if path.exists():
        target = BACKUP / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def restore():
    if BACKUP.exists():
        for item in BACKUP.rglob("*"):
            if item.is_file():
                target = ROOT / item.relative_to(BACKUP)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)


print("\nAJUSTE DE PERFIS NO PADRAO OFICIAL")
print(f"Projeto: {ROOT}")
print("Sera preservada a tela em cartoes aberta pelo menu Perfis.")
print("Nenhum CSS sera substituido.\n")

source = BACKEND.read_text(encoding="utf-8-sig")

# Identifica a rota e o template oficiais usados pelo menu /perfis.
list_route = route_block(source, "/perfis'", "get")
if not list_route:
    raise RuntimeError("Rota oficial GET /perfis nao encontrada. Nenhum arquivo foi alterado.")

list_block = list_route.group(0)
list_template_match = re.search(r"name\s*=\s*['\"]([^'\"]+\.html)['\"]", list_block)
if not list_template_match:
    list_template_match = re.search(r"TemplateResponse\([^\n]*['\"]([^'\"]+\.html)['\"]", list_block)
if not list_template_match:
    raise RuntimeError("Template oficial da lista de perfis nao identificado.")
list_template = TEMPLATES / list_template_match.group(1)
if not list_template.exists():
    raise RuntimeError(f"Template oficial nao encontrado: {list_template}")

# Identifica o detalhe oficial.
detail_route = route_block(source, "/perfis/{profile_id}", "get") or route_block(source, "/perfis/{perfil_id}", "get")
if not detail_route:
    raise RuntimeError("Rota oficial de detalhe /perfis/{id} nao encontrada.")
detail_block = detail_route.group(0)
detail_template_match = re.search(r"name\s*=\s*['\"]([^'\"]+\.html)['\"]", detail_block)
if not detail_template_match:
    detail_template_match = re.search(r"TemplateResponse\([^\n]*['\"]([^'\"]+\.html)['\"]", detail_block)
if not detail_template_match:
    raise RuntimeError("Template oficial do detalhe nao identificado.")
detail_template = TEMPLATES / detail_template_match.group(1)
if not detail_template.exists():
    raise RuntimeError(f"Template de detalhe nao encontrado: {detail_template}")

changed = {BACKEND, list_template, detail_template}
for path in changed:
    backup(path)

try:
    # Mantem /perfis como tela unica. Rotas antigas do portal apenas redirecionam.
    portal_list = route_block(source, "/portal/perfis'", "get")
    if portal_list:
        redirect = """@router.get('/portal/perfis')
def portal_profiles_redirect(user: Annotated[SystemUser, Depends(require_user)]):
    return RedirectResponse('/perfis', status_code=303)
"""
        source = source[:portal_list.start()] + redirect + "\n\n" + source[portal_list.end():]

    portal_detail = route_block(source, "/portal/perfis/{profile_id}'", "get")
    if portal_detail:
        redirect = """@router.get('/portal/perfis/{profile_id}')
def portal_profile_redirect(profile_id: int, user: Annotated[SystemUser, Depends(require_user)]):
    return RedirectResponse(f'/perfis/{profile_id}', status_code=303)
"""
        source = source[:portal_detail.start()] + redirect + "\n\n" + source[portal_detail.end():]

    # Remove somente rotas de situacao antigas para evitar conflito.
    for route in ["/portal/perfis/{profile_id}/situacao", "/perfis/{profile_id}/situacao"]:
        while True:
            old = route_block(source, route, "post")
            if not old:
                break
            source = source[:old.start()] + source[old.end():]

    # Endpoints novos: consulta a origem e inativa somente perfil gerado em proposta.
    endpoint = f'''\n\n# {MARK}\n@router.get('/api/perfis/{{profile_id}}/origem-proposta')
def profile_proposal_origin(profile_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    generated = session.scalar(
        select(func.count()).select_from(ProfileProposal).where(
            ProfileProposal.imported_result_profile_id == profile_id
        )
    )
    return {{'generated': bool(generated), 'can_manage': user.role == ROLE_ADMIN}}


@router.post('/perfis/{{profile_id}}/situacao')
def profile_status_update(
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
        raise HTTPException(409, 'Somente perfis gerados em propostas podem ser alterados por esta acao')
    if situacao not in {{'Ativo', 'Inativo'}}:
        raise HTTPException(400, 'Situacao invalida')
    profile.situacao = situacao
    profile.ultima_atualizacao = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f'/perfis/{{profile.id}}', status_code=303)
'''
    source = source.rstrip() + endpoint + "\n"

    # Preserva integralmente o HTML oficial e acrescenta apenas o filtro funcional.
    list_html = list_template.read_text(encoding="utf-8-sig")
    if MARK not in list_html:
        filter_html = f'''\n<!-- {MARK} -->\n<label class="proposal-origin-filter">\n  Origem\n  <select id="proposal-origin-filter">\n    <option value="all">Todos os perfis</option>\n    <option value="proposal">Gerados em proposta</option>\n    <option value="erp">Importados do ERP</option>\n  </select>\n</label>\n<script>\n(() => {{\n  const select = document.getElementById('proposal-origin-filter');\n  if (!select) return;\n  const cards = [...document.querySelectorAll('a[href^="/perfis/"], [data-profile-card]')].map(el => el.closest('article, .card, .profile-card, a') || el);\n  const uniqueCards = [...new Set(cards)];\n  const apply = () => uniqueCards.forEach(card => {{\n    const text = (card.textContent || '').toLowerCase();\n    const generated = text.includes('gerado na proposta') || text.includes('gerado em proposta');\n    card.hidden = select.value === 'proposal' ? !generated : select.value === 'erp' ? generated : false;\n  }});\n  select.addEventListener('change', apply);\n}})();\n</script>\n'''
        # Insere antes do fechamento do bloco, sem recriar a pagina.
        if "{% endblock %}" not in list_html:
            raise RuntimeError(f"Final do template nao encontrado: {list_template.name}")
        list_html = list_html.replace("{% endblock %}", filter_html + "{% endblock %}", 1)

    # Preserva o detalhe oficial e inclui botao somente se a API confirmar proposta + admin.
    detail_html = detail_template.read_text(encoding="utf-8-sig")
    detail_html = detail_html.replace('href="/portal/perfis"', 'href="/perfis"').replace("href='/portal/perfis'", "href='/perfis'")
    if MARK not in detail_html:
        variable = "profile" if "profile." in detail_html else "perfil"
        action_html = f'''\n<!-- {MARK} -->\n<section id="proposal-profile-actions" hidden>\n  <form method="post" action="/perfis/{{{{ {variable}.id }}}}/situacao">\n    <input type="hidden" name="situacao" value="{{{{ 'Inativo' if {variable}.situacao != 'Inativo' else 'Ativo' }}}}">\n    <button type="submit">{{{{ 'Inativar perfil' if {variable}.situacao != 'Inativo' else 'Reativar perfil' }}}}</button>\n  </form>\n</section>\n<script>\nfetch('/api/perfis/{{{{ {variable}.id }}}}/origem-proposta')\n  .then(response => response.ok ? response.json() : null)\n  .then(data => {{\n    if (data?.generated && data?.can_manage) {{\n      document.getElementById('proposal-profile-actions').hidden = false;\n    }}\n  }});\n</script>\n'''
        if "{% endblock %}" not in detail_html:
            raise RuntimeError(f"Final do template nao encontrado: {detail_template.name}")
        detail_html = detail_html.replace("{% endblock %}", action_html + "{% endblock %}", 1)

    BACKEND.write_text(source, encoding="utf-8")
    list_template.write_text(list_html, encoding="utf-8")
    detail_template.write_text(detail_html, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("[OK] Mantido o design oficial em cartoes da rota /perfis")
print("[OK] Filtro especifico 'Gerados em proposta' adicionado")
print("[OK] Inativar/Reativar liberado somente para perfil gerado em proposta e ADMIN")
print("[OK] Voltar e rotas antigas direcionados para /perfis")
print(f"\n[BACKUP] {BACKUP}")
print("[PRESERVADO] Nenhum CSS, cor ou estrutura da tela oficial foi substituido.")
print("\nReinicie o servidor e pressione Ctrl + F5.")
