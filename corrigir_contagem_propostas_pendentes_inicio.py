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
BACKUP = ROOT / f"backup_propostas_pendentes_inicio_{STAMP}"
PENDING_STATUS = "EM_REVISAO"
MARKER = "CONTAGEM_SOMENTE_PROPOSTAS_PENDENTES_V1"

if not BACKEND.exists():
    raise RuntimeError(f"Arquivo nao encontrado: {BACKEND}")


def route_block(source: str, route_piece: str, method: str = "get") -> re.Match[str]:
    pattern = re.compile(
        rf"(?ms)^@router\.{method}\([^\n]*{re.escape(route_piece)}[^\n]*\)\s*\n"
        rf"def\s+\w+\(.*?(?=^@router\.|\Z)"
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError(f"Rota nao encontrada: {method.upper()} {route_piece}")
    return match


def backup(path: Path) -> None:
    target = BACKUP / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore() -> None:
    if not BACKUP.exists():
        return
    for source in BACKUP.rglob("*"):
        if source.is_file():
            target = ROOT / source.relative_to(BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


print("\nCORRECAO DAS PROPOSTAS PENDENTES NA TELA INICIAL")
print(f"Projeto: {ROOT}")
print(f"Status considerado pendente: {PENDING_STATUS}\n")

source = BACKEND.read_text(encoding="utf-8-sig")
original = source

# 1. A tela de propostas passa a listar exclusivamente itens em revisao.
proposals_match = route_block(source, "/portal/propostas'", "get")
proposals_route = proposals_match.group(0)

# Remove filtros anteriores de concluido e aplica uma unica regra de pendencia.
proposals_route = re.sub(
    r"\.where\(ProfileProposal\.workflow_status\.not_in\([^\n]+\)\)",
    "",
    proposals_route,
)
proposals_route = re.sub(
    r"\.where\(ProfileProposal\.workflow_status\s*==\s*['\"][^'\"]+['\"]\)",
    "",
    proposals_route,
)

query_anchor = re.search(
    r"(?m)^(?P<i>\s*)query\s*=\s*\(\s*\n(?P<body>.*?)(?P=i)\)\s*$",
    proposals_route,
    flags=re.S,
)
if query_anchor:
    block = query_anchor.group(0)
    order_marker = ".order_by(ProfileProposal.created_at.desc())"
    if order_marker not in block:
        raise RuntimeError("Ordenacao da lista de propostas nao encontrada. Nenhum arquivo foi alterado.")
    block = block.replace(
        order_marker,
        f".where(ProfileProposal.workflow_status == '{PENDING_STATUS}')\n        {order_marker}",
        1,
    )
    proposals_route = proposals_route[:query_anchor.start()] + block + proposals_route[query_anchor.end():]
else:
    single_query = re.search(r"(?m)^(?P<i>\s*)query\s*=\s*select\(ProfileProposal\).*?$", proposals_route)
    if not single_query:
        raise RuntimeError("Consulta da lista de propostas nao reconhecida. Nenhum arquivo foi alterado.")
    line = single_query.group(0)
    if ".order_by(" in line:
        line = line.replace(
            ".order_by(",
            f".where(ProfileProposal.workflow_status == '{PENDING_STATUS}').order_by(",
            1,
        )
    else:
        line += f".where(ProfileProposal.workflow_status == '{PENDING_STATUS}')"
    proposals_route = proposals_route[:single_query.start()] + line + proposals_route[single_query.end():]

source = source[:proposals_match.start()] + proposals_route.rstrip() + "\n\n\n" + source[proposals_match.end():]
print("[OK] Tela de propostas limitada a pendentes")

# 2. Localiza o template inicial pelo texto visivel e descobre a variavel do numero.
home_template = None
count_variable = None
for template in TEMPLATES.rglob("*.html"):
    text = template.read_text(encoding="utf-8-sig", errors="ignore")
    phrase = re.search(r"Propostas\s+no\s+seu\s+escopo", text, flags=re.I)
    if not phrase:
        continue
    home_template = template
    around = text[phrase.end(): phrase.end() + 500]
    variable = re.search(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", around)
    if variable:
        count_variable = variable.group(1)
        break

if not home_template or not count_variable:
    raise RuntimeError("Template inicial ou variavel da contagem nao identificados. Nenhum arquivo foi alterado.")
print(f"[OK] Template inicial identificado: {home_template.relative_to(ROOT)}")
print(f"[OK] Variavel da contagem identificada: {count_variable}")

# 3. Localiza a rota que renderiza esse template e sobrescreve a mesma variavel
# imediatamente antes do TemplateResponse, respeitando o escopo de gerente.
template_name = home_template.relative_to(TEMPLATES).as_posix()
response_pos = source.find(f"name='{template_name}'")
if response_pos < 0:
    response_pos = source.find(f'name="{template_name}"')
if response_pos < 0:
    response_pos = source.find(f"'{template_name}'")
if response_pos < 0:
    raise RuntimeError(f"Rota que renderiza {template_name} nao encontrada.")

route_start = source.rfind("\n@router.get", 0, response_pos)
route_end = source.find("\n@router.", response_pos)
if route_start < 0:
    raise RuntimeError("Inicio da rota inicial nao encontrado.")
if route_end < 0:
    route_end = len(source)
home_route = source[route_start + 1:route_end]

if MARKER not in home_route:
    return_pos = home_route.find("return templates.TemplateResponse")
    if return_pos < 0:
        raise RuntimeError("TemplateResponse da tela inicial nao encontrado.")

    indent_match = re.search(r"(?m)^(\s*)return templates\.TemplateResponse", home_route)
    indent = indent_match.group(1) if indent_match else "    "
    code = f'''{indent}# {MARKER}\n{indent}pending_proposals_query = select(func.count()).select_from(ProfileProposal).where(\n{indent}    ProfileProposal.workflow_status == '{PENDING_STATUS}'\n{indent})\n{indent}if user.role == ROLE_MANAGER:\n{indent}    pending_proposals_query = pending_proposals_query.where(\n{indent}        ProfileProposal.department_id == user.department_id\n{indent}    )\n{indent}{count_variable} = session.scalar(pending_proposals_query) or 0\n\n'''
    home_route = home_route[:return_pos] + code + home_route[return_pos:]

    # Garante que o contexto utilize a variavel recalculada. Se ela ja estiver no
    # contexto, a atribuicao acima basta e nao e feita nenhuma segunda alteracao.
    source = source[:route_start + 1] + home_route.rstrip() + "\n\n" + source[route_end:]

print("[OK] Cartao inicial conta somente propostas pendentes")

if source == original:
    print("[OK] A correcao ja estava aplicada. Nenhuma gravacao foi necessaria.")
    raise SystemExit(0)

backup(BACKEND)
try:
    BACKEND.write_text(source, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("\n[SUCESSO] Contagem e listagem sincronizadas.")
print("[COMPORTAMENTO] Ao finalizar uma proposta, ela sai da lista de pendentes.")
print("[COMPORTAMENTO] O numero da tela inicial diminui na proxima abertura/atualizacao.")
print("[PRESERVADO] Perfis, usuarios, arvores, filtros e CSS nao foram alterados.")
print(f"[BACKUP] {BACKUP}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
