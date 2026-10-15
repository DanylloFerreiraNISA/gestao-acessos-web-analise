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
BACKUP = ROOT / f"backup_unificar_perfis_{STAMP}"

if not BACKEND.exists():
    raise RuntimeError(f"Arquivo nao encontrado: {BACKEND}")

source = BACKEND.read_text(encoding="utf-8-sig")
changed: set[Path] = {BACKEND}


def route_block(text: str, route: str, method: str = "get") -> re.Match[str] | None:
    pattern = re.compile(
        rf"(?ms)^@router\.{method}\([^\n]*{re.escape(route)}[^\n]*\)\s*\n"
        rf"def\s+\w+\(.*?(?=^@router\.|\Z)"
    )
    return pattern.search(text)


def replace_block(text: str, match: re.Match[str], replacement: str) -> str:
    return text[: match.start()] + replacement.rstrip() + "\n\n\n" + text[match.end() :]


def backup(path: Path) -> None:
    if path.exists():
        destination = BACKUP / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def restore() -> None:
    if not BACKUP.exists():
        return
    for item in BACKUP.rglob("*"):
        if item.is_file():
            destination = ROOT / item.relative_to(BACKUP)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


print("\nUNIFICACAO DA TELA DE PERFIS E CORRECAO DA INATIVACAO")
print(f"Projeto: {ROOT}")
print("A tela oficial sera a mesma aberta pelo item Perfis do menu: /perfis")
print("Nenhum CSS sera alterado.\n")

# Descobre qual template a rota oficial /perfis/{profile_id} utiliza.
detail_route = route_block(source, "/perfis/{profile_id}", "get")
if detail_route is None:
    detail_route = route_block(source, "/perfis/{perfil_id}", "get")
if detail_route is None:
    raise RuntimeError("A rota oficial de detalhe /perfis/{id} nao foi encontrada. Nenhum arquivo foi alterado.")

detail_text = detail_route.group(0)
template_match = re.search(r"name\s*=\s*['\"]([^'\"]+\.html)['\"]", detail_text)
if not template_match:
    template_match = re.search(r"TemplateResponse\([^\n]*['\"]([^'\"]+\.html)['\"]", detail_text)
if not template_match:
    raise RuntimeError("Nao foi possivel identificar o template do detalhe do perfil.")

detail_template = TEMPLATES / template_match.group(1)
if not detail_template.exists():
    raise RuntimeError(f"Template de detalhe nao encontrado: {detail_template}")
changed.add(detail_template)

# 1. /portal/perfis passa a redirecionar para a tela oficial do menu.
portal_list = route_block(source, "/portal/perfis'", "get")
if portal_list:
    replacement = """@router.get('/portal/perfis')
def portal_profiles_redirect(user: Annotated[SystemUser, Depends(require_user)]):
    return RedirectResponse('/perfis', status_code=303)
"""
    source = replace_block(source, portal_list, replacement)
    print("[OK] /portal/perfis agora abre a mesma tela do menu /perfis")
else:
    print("[OK] Nao havia rota alternativa /portal/perfis")

# 2. Detalhe alternativo tambem redireciona para o detalhe oficial.
portal_detail = route_block(source, "/portal/perfis/{profile_id}'", "get")
if portal_detail:
    replacement = """@router.get('/portal/perfis/{profile_id}')
def portal_profile_redirect(profile_id: int, user: Annotated[SystemUser, Depends(require_user)]):
    return RedirectResponse(f'/perfis/{profile_id}', status_code=303)
"""
    source = replace_block(source, portal_detail, replacement)
    print("[OK] detalhes alternativos agora usam a tela oficial")

# 3. Remove rotas antigas de situacao para evitar conflito.
for route in ["/portal/perfis/{profile_id}/situacao", "/perfis/{profile_id}/situacao"]:
    while True:
        old = route_block(source, route, "post")
        if not old:
            break
        source = source[: old.start()] + source[old.end() :]

# 4. Cria uma unica rota de ativacao/inativacao e volta ao detalhe oficial.
status_route = """@router.post('/perfis/{profile_id}/situacao')
def profile_status_update(
    profile_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    situacao: Annotated[str, Form()],
):
    profile = session.get(Perfil, profile_id)
    if not profile:
        raise HTTPException(404, 'Perfil nao encontrado')
    if situacao not in {'Ativo', 'Inativo'}:
        raise HTTPException(400, 'Situacao invalida')
    profile.situacao = situacao
    profile.ultima_atualizacao = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f'/perfis/{profile.id}', status_code=303)


"""
insert_position = detail_route.end()
# Recalcula posicao usando a fonte ja alterada.
current_detail = route_block(source, "/perfis/{profile_id}", "get") or route_block(source, "/perfis/{perfil_id}", "get")
if current_detail is None:
    raise RuntimeError("A rota oficial de detalhe desapareceu durante a atualizacao.")
insert_position = current_detail.end()
source = source[:insert_position] + "\n\n" + status_route + source[insert_position:]
print("[OK] rota unica de inativar/reativar criada")

# 5. Preserva integralmente o design do template oficial e apenas injeta o controle.
template = detail_template.read_text(encoding="utf-8-sig")
# Corrige somente links de retorno que apontavam para a tela paralela.
template = template.replace('href="/portal/perfis"', 'href="/perfis"')
template = template.replace("href='/portal/perfis'", "href='/perfis'")

if "/perfis/{{ profile.id }}/situacao" not in template and "/perfis/{{ perfil.id }}/situacao" not in template:
    variable = "profile" if "profile." in template else "perfil"
    form = f'''\n<section class="profile-status-actions">\n  {{% if user.role in ['ADMIN_TI', 'ADMIN'] %}}\n  <form method="post" action="/perfis/{{{{ {variable}.id }}}}/situacao">\n    <input type="hidden" name="situacao" value="{{{{ 'Inativo' if {variable}.situacao != 'Inativo' else 'Ativo' }}}}">\n    <button type="submit">{{{{ 'Inativar perfil' if {variable}.situacao != 'Inativo' else 'Reativar perfil' }}}}</button>\n  </form>\n  {{% endif %}}\n</section>\n'''
    if "{% endblock %}" not in template:
        raise RuntimeError(f"Nao foi possivel identificar o final do template {detail_template.name}")
    template = template.replace("{% endblock %}", form + "{% endblock %}", 1)
    print(f"[OK] botao de inativacao adicionado sem substituir o design de {detail_template.name}")
else:
    print("[OK] template oficial ja possuia controle de situacao")

# 6. Corrige outros templates que tenham link Voltar para a tela paralela, sem mudar estrutura.
for path in TEMPLATES.glob("*.html"):
    text = path.read_text(encoding="utf-8-sig")
    updated = text.replace('href="/portal/perfis"', 'href="/perfis"').replace("href='/portal/perfis'", "href='/perfis'")
    if updated != text:
        changed.add(path)

for path in changed:
    backup(path)

try:
    BACKEND.write_text(source, encoding="utf-8")
    detail_template.write_text(template, encoding="utf-8")
    for path in changed:
        if path in {BACKEND, detail_template}:
            continue
        text = path.read_text(encoding="utf-8-sig")
        text = text.replace('href="/portal/perfis"', 'href="/perfis"').replace("href='/portal/perfis'", "href='/perfis'")
        path.write_text(text, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("\n[SUCESSO] Tela de perfis unificada e inativacao corrigida.")
print(f"[TELA OFICIAL] /perfis")
print(f"[TEMPLATE PRESERVADO] {detail_template.relative_to(ROOT)}")
print(f"[BACKUP] {BACKUP}")
print("[PRESERVADO] Nenhum CSS, cor ou layout da lista oficial foi substituido.")
print("\nReinicie o servidor e pressione Ctrl + F5.")
