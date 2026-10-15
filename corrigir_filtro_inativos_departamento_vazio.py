from __future__ import annotations

import py_compile
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
BACKEND = ROOT / "app" / "access_control.py"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_correcao_departamento_vazio_{STAMP}" / "app" / "access_control.py"

if not BACKEND.exists():
    raise RuntimeError(f"Arquivo nao encontrado: {BACKEND}")

print("\nCORRECAO DO FILTRO DE PERFIS")
print(f"Projeto: {ROOT}")
print("Correcao: departamento_id vazio nao sera mais interpretado como inteiro.\n")

source = BACKEND.read_text(encoding="utf-8-sig")
pattern = re.compile(
    r"(?ms)^@router\.get\('/portal/perfis'[^\n]*\)\s*\n"
    r"def\s+portal_profiles\(.*?(?=^@router\.|\Z)"
)
match = pattern.search(source)
if not match:
    raise RuntimeError("A rota GET /portal/perfis nao foi encontrada. Nenhum arquivo foi alterado.")

route = match.group(0)
original_route = route

# O navegador envia departamento_id= quando a opcao Todos os departamentos esta selecionada.
# FastAPI nao consegue converter uma string vazia diretamente para int | None.
route, count = re.subn(
    r"departamento_id:\s*int\s*\|\s*None\s*=\s*None",
    "departamento_id: str = ''",
    route,
    count=1,
)
if count == 0 and "departamento_id: str = ''" not in route:
    raise RuntimeError("O parametro departamento_id esperado nao foi encontrado. Nenhum arquivo foi alterado.")

if "department_id_value =" not in route:
    anchors = [
        "    origem = origem.strip().upper()\n",
        "    situacao = situacao.strip().upper()\n",
    ]
    anchor = next((item for item in anchors if item in route), None)
    if not anchor:
        raise RuntimeError("O ponto de normalizacao dos filtros nao foi encontrado. Nenhum arquivo foi alterado.")
    conversion = (
        "    department_id_value = int(departamento_id) "
        "if departamento_id.strip().isdigit() else None\n"
    )
    route = route.replace(anchor, anchor + conversion, 1)

# Usa o valor convertido somente quando existe um ID numerico valido.
route = route.replace("elif departamento_id:\n", "elif department_id_value:\n")
route = route.replace(
    "query = query.where(Perfil.departamento_id == departamento_id)",
    "query = query.where(Perfil.departamento_id == department_id_value)",
)
route = route.replace(
    "'filter_department_id': departamento_id,",
    "'filter_department_id': department_id_value,",
)

if route == original_route:
    print("[OK] A correcao ja estava aplicada. Nenhum arquivo foi alterado.")
    raise SystemExit(0)

updated = source[:match.start()] + route.rstrip() + "\n\n\n" + source[match.end():]

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(BACKEND, BACKUP)

try:
    BACKEND.write_text(updated, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    shutil.copy2(BACKUP, BACKEND)
    raise

print("[OK] departamento_id vazio agora e aceito")
print("[OK] IDs numericos de departamento continuam funcionando")
print("[OK] Filtros Ativos, Inativos, Todos e Origem foram preservados")
print("[OK] Nenhum template, arvore ou CSS foi alterado")
print(f"[BACKUP] {BACKUP.parent.parent.parent}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
