from __future__ import annotations

import py_compile
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
BACKEND = ROOT / "app" / "access_control.py"
TEMPLATE = ROOT / "app" / "templates" / "portal_profiles.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_filtro_status_perfis_{STAMP}"

for path in (BACKEND, TEMPLATE):
    if not path.exists():
        raise RuntimeError(f"Arquivo necessario nao encontrado: {path}")


def backup(path: Path) -> None:
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def restore() -> None:
    for source in BACKUP.rglob("*"):
        if source.is_file():
            target = ROOT / source.relative_to(BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def route_block(source: str) -> re.Match[str]:
    pattern = re.compile(
        r"(?ms)^@router\.get\('/portal/perfis'[^\n]*\)\s*\n"
        r"def\s+portal_profiles\(.*?(?=^@router\.|\Z)"
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError("A rota GET /portal/perfis nao foi encontrada. Nenhum arquivo foi alterado.")
    return match


print("\nFILTRO DE PERFIS ATIVOS E INATIVOS")
print(f"Projeto: {ROOT}")
print("Por padrao, somente perfis ativos serao exibidos.\n")

backend = BACKEND.read_text(encoding="utf-8-sig")
match = route_block(backend)
current_route = match.group(0)

# Preserva a rota atual e aplica mudanças estruturais pequenas e verificáveis.
if "situacao: str = 'ATIVO'" not in current_route:
    current_route, count = re.subn(
        r"(\s+origem:\s*str\s*=\s*''\s*,\s*\n)(\s*\):)",
        r"\1    situacao: str = 'ATIVO',\n\2",
        current_route,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Nao foi possivel adicionar o parametro situacao na rota. Nenhum arquivo foi alterado.")

if "situacao = situacao.strip().upper()" not in current_route:
    anchor = "    origem = origem.strip().upper()\n"
    if anchor not in current_route:
        raise RuntimeError("O tratamento do filtro origem nao foi encontrado. Nenhum arquivo foi alterado.")
    current_route = current_route.replace(
        anchor,
        anchor + "    situacao = situacao.strip().upper()\n",
        1,
    )

if "if situacao == 'INATIVO':" not in current_route:
    anchor = "    if origem == 'PROPOSTA':\n"
    if anchor not in current_route:
        raise RuntimeError("O ponto de insercao antes do filtro de origem nao foi encontrado.")
    status_code = """    if situacao == 'INATIVO':
        query = query.where(func.upper(Perfil.situacao) == 'INATIVO')
    elif situacao == 'TODOS':
        pass
    else:
        query = query.where(func.upper(Perfil.situacao).in_({'ATIVO', 'COMPLETO', 'PENDENTE'}))
"""
    current_route = current_route.replace(anchor, status_code + anchor, 1)

if "'filter_status': situacao," not in current_route:
    anchor = "            'filter_origin': origem,\n"
    if anchor not in current_route:
        raise RuntimeError("O contexto filter_origin nao foi encontrado.")
    current_route = current_route.replace(
        anchor,
        anchor + "            'filter_status': situacao,\n",
        1,
    )

backend = backend[:match.start()] + current_route.rstrip() + "\n\n\n" + backend[match.end():]

template = TEMPLATE.read_text(encoding="utf-8-sig")

# Acrescenta o filtro no formulário visual existente, mantendo o design escolhido.
if 'name="situacao"' not in template:
    origin_label = '''  <label>Origem<select name="origem"><option value="">Todos os perfis</option><option value="PROPOSTA" {% if filter_origin == 'PROPOSTA' %}selected{% endif %}>Gerados em proposta</option><option value="ERP" {% if filter_origin == 'ERP' %}selected{% endif %}>Importados do ERP</option></select></label>'''
    if origin_label not in template:
        raise RuntimeError("O filtro Origem esperado nao foi encontrado no template. Nenhum arquivo foi alterado.")
    status_label = '''  <label>Situação<select name="situacao"><option value="ATIVO" {% if filter_status == 'ATIVO' %}selected{% endif %}>Ativos</option><option value="INATIVO" {% if filter_status == 'INATIVO' %}selected{% endif %}>Inativos</option><option value="TODOS" {% if filter_status == 'TODOS' %}selected{% endif %}>Todos</option></select></label>'''
    template = template.replace(origin_label, origin_label + "\n" + status_label, 1)

for path in (BACKEND, TEMPLATE):
    backup(path)

try:
    BACKEND.write_text(backend, encoding="utf-8")
    TEMPLATE.write_text(template, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("[OK] Perfis inativos deixam de aparecer na visualizacao inicial")
print("[OK] Filtro Ativos, Inativos e Todos adicionado")
print("[OK] Filtro de origem Gerados em proposta foi preservado")
print("[OK] Layout, arvore classica e CSS nao foram alterados")
print(f"[BACKUP] {BACKUP}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
