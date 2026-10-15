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
BACKUP = ROOT / f"backup_perfis_padrao_v2_{STAMP}"
MARK = "PERFIS_PADRAO_PROPOSTA_V2"

if not BACKEND.exists():
    raise RuntimeError(f"Arquivo nao encontrado: {BACKEND}")
if not TEMPLATES.exists():
    raise RuntimeError(f"Pasta de templates nao encontrada: {TEMPLATES}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="strict")


def route_block(text: str, route: str, method: str = "get"):
    pattern = re.compile(
        rf"(?ms)^@router\.{method}\([^\n]*{re.escape(route)}[^\n]*\)\s*\n"
        rf"def\s+\w+\(.*?(?=^@router\.|\Z)"
    )
    return pattern.search(text)


def backup(path: Path) -> None:
    if path.exists():
        target = BACKUP / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def restore() -> None:
    if not BACKUP.exists():
        return
    for item in BACKUP.rglob("*"):
        if item.is_file():
            target = ROOT / item.relative_to(BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def find_official_list_template() -> Path:
    scored: list[tuple[int, Path]] = []
    for path in TEMPLATES.rglob("*.html"):
        text = read(path).lower()
        score = 0
        if "perfis importados do erp" in text: score += 100
        if "todos os perfis disponíveis" in text or "todos os perfis disponiveis" in text: score += 80
        if "pesquisar por nome" in text: score += 40
        if "todos os departamentos" in text: score += 30
        if "perfil(is) encontrado" in text: score += 30
        if "profile-card" in text or "profiles-grid" in text or "card" in text: score += 10
        if score: scored.append((score, path))
    if not scored:
        raise RuntimeError("Nao localizei o template em cartoes mostrado na imagem. Nenhum arquivo foi alterado.")
    scored.sort(key=lambda item: (-item[0], str(item[1])))
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        names = "\n".join(str(p) for score, p in scored if score == scored[0][0])
        raise RuntimeError(f"Mais de um template oficial foi encontrado com a mesma pontuacao:\n{names}")
    return scored[0][1]


def find_detail_template(list_template: Path) -> Path:
    candidates: list[tuple[int, Path]] = []
    for path in TEMPLATES.rglob("*.html"):
        if path == list_template:
            continue
        text = read(path).lower()
        score = 0
        if "voltar" in text and "perfil" in text: score += 45
        if "acessos" in text: score += 25
        if "usuarios" in text or "usuários" in text: score += 10
        if "profile" in path.name.lower() or "perfil" in path.name.lower(): score += 20
        if "{{ profile." in text or "{{ perfil." in text: score += 30
        if score >= 45: candidates.append((score, path))
    if not candidates:
        raise RuntimeError("Nao localizei o template oficial de detalhe do perfil. Nenhum arquivo foi alterado.")
    candidates.sort(key=lambda item: (-item[0], str(item[1])))
    return candidates[0][1]


print("\nAJUSTE DE PERFIS NO PADRAO OFICIAL - V2")
print(f"Projeto: {ROOT}")
print("A tela oficial sera identificada pelo conteudo visual da imagem, nao pelo nome do arquivo.")
print("Nenhum CSS sera alterado.\n")

list_template = find_official_list_template()
detail_template = find_detail_template(list_template)
print(f"[ENCONTRADO] Lista oficial: {list_template.relative_to(ROOT)}")
print(f"[ENCONTRADO] Detalhe oficial: {detail_template.relative_to(ROOT)}")

source = read(BACKEND)
changed = {BACKEND, list_template, detail_template}
for path in changed:
    backup(path)

try:
    # Remove endpoints V1/V2 anteriores para evitar duplicidade.
    old_marker = source.find("# PERFIS_PROPOSTA_PADRAO_V1")
    if old_marker >= 0:
        source = source[:old_marker].rstrip() + "\n"
    old_marker = source.find("# PERFIS_PADRAO_PROPOSTA_V2")
    if old_marker >= 0:
        source = source[:old_marker].rstrip() + "\n"

    # Rotas alternativas sempre voltam ao padrao oficial /perfis.
    for route, replacement in [
        ("/portal/perfis'", """@router.get('/portal/perfis')
def portal_profiles_redirect(user: Annotated[SystemUser, Depends(require_user)]):
    return RedirectResponse('/perfis', status_code=303)
"""),
        ("/portal/perfis/{profile_id}'", """@router.get('/portal/perfis/{profile_id}')
def portal_profile_redirect(profile_id: int, user: Annotated[SystemUser, Depends(require_user)]):
    return RedirectResponse(f'/perfis/{profile_id}', status_code=303)
"""),
    ]:
        match = route_block(source, route, "get")
        if match:
            source = source[:match.start()] + replacement + "\n\n" + source[match.end():]

    # Remove rotas antigas de situacao.
    for route in ["/portal/perfis/{profile_id}/situacao", "/perfis/{profile_id}/situacao"]:
        while True:
            match = route_block(source, route, "post")
            if not match: break
            source = source[:match.start()] + source[match.end():]

    endpoints = f'''\n\n# {MARK}\n@router.get('/api/perfis/origens-proposta')
def proposal_profile_origins(session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    ids = session.scalars(
        select(ProfileProposal.imported_result_profile_id).where(
            ProfileProposal.imported_result_profile_id.is_not(None)
        )
    ).all()
    return {{'profile_ids': [int(value) for value in ids]}}


@router.get('/api/perfis/{{profile_id}}/origem-proposta')
def proposal_profile_origin(profile_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    generated = session.scalar(
        select(func.count()).select_from(ProfileProposal).where(
            ProfileProposal.imported_result_profile_id == profile_id
        )
    )
    return {{'generated': bool(generated), 'can_manage': user.role == ROLE_ADMIN}}


@router.post('/perfis/{{profile_id}}/situacao')
def profile_status_update(profile_id: int, session: Db, user: Annotated[SystemUser, Depends(require_admin)], situacao: Annotated[str, Form()]):
    profile = session.get(Perfil, profile_id)
    if not profile:
        raise HTTPException(404, 'Perfil nao encontrado')
    generated = session.scalar(
        select(func.count()).select_from(ProfileProposal).where(
            ProfileProposal.imported_result_profile_id == profile_id
        )
    )
    if not generated:
        raise HTTPException(409, 'Somente perfis gerados em propostas podem ser inativados por esta acao')
    if situacao not in {{'Ativo', 'Inativo'}}:
        raise HTTPException(400, 'Situacao invalida')
    profile.situacao = situacao
    profile.ultima_atualizacao = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f'/perfis/{{profile.id}}', status_code=303)
'''
    source = source.rstrip() + endpoints + "\n"

    # Injeta apenas um filtro flutuante no formulario existente e marca os cartoes via API.
    list_html = read(list_template)
    if MARK not in list_html:
        addition = f'''\n<!-- {MARK} -->\n<script>\ndocument.addEventListener('DOMContentLoaded', async () => {{\n  const response = await fetch('/api/perfis/origens-proposta');\n  if (!response.ok) return;\n  const data = await response.json();\n  const generatedIds = new Set((data.profile_ids || []).map(String));\n  const links = [...document.querySelectorAll('a[href^="/perfis/"]')];\n  const cards = [];\n  for (const link of links) {{\n    const match = link.getAttribute('href').match(/^\\/perfis\\/(\\d+)$/);\n    if (!match) continue;\n    const card = link.closest('[class*="card"], article, li') || link;\n    card.dataset.profileOrigin = generatedIds.has(match[1]) ? 'proposal' : 'erp';\n    if (generatedIds.has(match[1]) && !card.textContent.includes('Gerado na proposta')) {{\n      const label = document.createElement('small');\n      label.textContent = 'Gerado na proposta';\n      label.style.display = 'block';\n      card.appendChild(label);\n    }}\n    cards.push(card);\n  }}\n  const originalForm = document.querySelector('form');\n  if (!originalForm || document.getElementById('profile-origin-filter')) return;\n  const wrapper = document.createElement('label');\n  wrapper.innerHTML = 'Origem <select id="profile-origin-filter"><option value="all">Todos os perfis</option><option value="proposal">Gerados em proposta</option><option value="erp">Importados do ERP</option></select>';
  originalForm.insertBefore(wrapper, originalForm.lastElementChild);\n  wrapper.querySelector('select').addEventListener('change', event => {{\n    cards.forEach(card => card.hidden = event.target.value !== 'all' && card.dataset.profileOrigin !== event.target.value);\n  }});\n}});\n</script>\n'''
        if "{% endblock %}" not in list_html:
            raise RuntimeError(f"Final do template nao encontrado: {list_template.name}")
        list_html = list_html.replace("{% endblock %}", addition + "{% endblock %}", 1)

    detail_html = read(detail_template)
    detail_html = detail_html.replace('href="/portal/perfis"', 'href="/perfis"').replace("href='/portal/perfis'", "href='/perfis'")
    if MARK not in detail_html:
        variable = "profile" if "profile." in detail_html else "perfil"
        addition = f'''\n<!-- {MARK} -->\n<section id="proposal-profile-actions" hidden>\n  <form method="post" action="/perfis/{{{{ {variable}.id }}}}/situacao">\n    <input type="hidden" name="situacao" value="{{{{ 'Inativo' if {variable}.situacao != 'Inativo' else 'Ativo' }}}}">\n    <button type="submit">{{{{ 'Inativar perfil' if {variable}.situacao != 'Inativo' else 'Reativar perfil' }}}}</button>\n  </form>\n</section>\n<script>\nfetch('/api/perfis/{{{{ {variable}.id }}}}/origem-proposta')\n .then(response => response.ok ? response.json() : null)\n .then(data => {{ if (data?.generated && data?.can_manage) document.getElementById('proposal-profile-actions').hidden = false; }});\n</script>\n'''
        if "{% endblock %}" not in detail_html:
            raise RuntimeError(f"Final do template nao encontrado: {detail_template.name}")
        detail_html = detail_html.replace("{% endblock %}", addition + "{% endblock %}", 1)

    BACKEND.write_text(source, encoding="utf-8")
    list_template.write_text(list_html, encoding="utf-8")
    detail_template.write_text(detail_html, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("\n[SUCESSO] Ajuste aplicado no template correto.")
print("[OK] Padrao visual em cartoes preservado")
print("[OK] Filtro Gerados em proposta adicionado")
print("[OK] Inativar/Reativar disponivel para perfil proposto e ADMIN")
print("[OK] Voltar sempre retorna para /perfis")
print(f"[BACKUP] {BACKUP}")
print("[PRESERVADO] Nenhum CSS foi alterado.")
print("\nReinicie o servidor e pressione Ctrl + F5.")
