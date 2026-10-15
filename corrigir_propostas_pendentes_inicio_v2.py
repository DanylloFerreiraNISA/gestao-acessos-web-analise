from __future__ import annotations

import py_compile
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
BACKEND = ROOT / 'app' / 'access_control.py'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
BACKUP = ROOT / f'backup_propostas_pendentes_v2_{STAMP}' / 'app' / 'access_control.py'
STATUS = 'EM_REVISAO'

if not BACKEND.exists():
    raise RuntimeError(f'Arquivo nao encontrado: {BACKEND}')


def function_with_text(source: str, required_text: str) -> tuple[int, int, str]:
    position = source.find(required_text)
    if position < 0:
        raise RuntimeError(f'Trecho nao encontrado: {required_text}')
    route_start = source.rfind('\n@router.', 0, position)
    if route_start < 0:
        route_start = source.find('@router.', 0, position)
    else:
        route_start += 1
    route_end = source.find('\n@router.', position)
    if route_end < 0:
        route_end = len(source)
    block = source[route_start:route_end]
    if '\ndef ' not in block:
        raise RuntimeError(f'Funcao da rota nao localizada para: {required_text}')
    return route_start, route_end, block


def add_status_to_query(block: str, variable: str) -> str:
    marker = f"ProfileProposal.workflow_status == '{STATUS}'"
    if marker in block:
        return block

    # Formato em varias linhas: variavel = ( select(...) ... )
    multi = re.search(
        rf"(?ms)^(?P<indent>\s*){re.escape(variable)}\s*=\s*\(\s*\n(?P<body>.*?)(?P=indent)\)\s*$",
        block,
    )
    if multi:
        query = multi.group(0)
        order = re.search(r'(?m)^(?P<i>\s*)\.order_by\(', query)
        if order:
            insert_at = order.start()
            indent = order.group('i')
            query = query[:insert_at] + f"{indent}.where(ProfileProposal.workflow_status == '{STATUS}')\n" + query[insert_at:]
        else:
            close = query.rfind(')')
            base_indent = multi.group('indent') + '    '
            query = query[:close] + f"{base_indent}.where(ProfileProposal.workflow_status == '{STATUS}')\n" + query[close:]
        return block[:multi.start()] + query + block[multi.end():]

    # Formato em uma linha.
    single = re.search(
        rf"(?m)^(?P<indent>\s*){re.escape(variable)}\s*=\s*(?P<query>select\(func\.count\(\)\)\.select_from\(ProfileProposal\)|select\(ProfileProposal\)[^\n]*)$",
        block,
    )
    if not single:
        raise RuntimeError(f'Consulta {variable} nao reconhecida.')

    line = single.group(0)
    line += f".where(ProfileProposal.workflow_status == '{STATUS}')"
    return block[:single.start()] + line + block[single.end():]


print('\nCORRECAO DE PROPOSTAS PENDENTES - V2')
print(f'Projeto: {ROOT}')
print('A validacao sera feita antes de substituir o arquivo ativo.\n')

source = BACKEND.read_text(encoding='utf-8-sig')
updated = source

# Tela inicial: altera a propria proposal_query usada no retorno atual.
start, end, home = function_with_text(updated, "name='portal.html'")
home = add_status_to_query(home, 'proposal_query')
updated = updated[:start] + home.rstrip() + '\n\n' + updated[end:]
print('[OK] Contador inicial usa somente EM_REVISAO')

# Tela de propostas: altera a query existente, sem recriar a funcao.
start, end, proposals = function_with_text(updated, "name='proposals.html'")
# Remove apenas filtros antigos de encerrados para deixar uma regra unica.
proposals = re.sub(
    r"(?m)^\s*\.where\(ProfileProposal\.workflow_status\.not_in\([^\n]+\)\)\s*\n?",
    '',
    proposals,
)
proposals = add_status_to_query(proposals, 'query')
updated = updated[:start] + proposals.rstrip() + '\n\n' + updated[end:]
print('[OK] Lista interna usa somente EM_REVISAO')

if updated == source:
    print('[OK] A correcao ja estava aplicada. Nenhum arquivo foi alterado.')
    raise SystemExit(0)

# Valida uma copia temporaria antes de tocar no arquivo ativo.
with tempfile.NamedTemporaryFile('w', suffix='.py', encoding='utf-8', delete=False) as temp:
    temp.write(updated)
    temp_path = Path(temp.name)
try:
    py_compile.compile(str(temp_path), doraise=True)
finally:
    temp_path.unlink(missing_ok=True)

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(BACKEND, BACKUP)
try:
    BACKEND.write_text(updated, encoding='utf-8')
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    shutil.copy2(BACKUP, BACKEND)
    raise

print('\n[SUCESSO] Contador e lista agora mostram somente propostas pendentes.')
print('[COMPORTAMENTO] Ao aprovar, rejeitar ou finalizar, a proposta sai da lista.')
print('[COMPORTAMENTO] Ao atualizar a tela inicial, o numero diminui automaticamente.')
print('[PRESERVADO] Nenhum template, CSS, perfil, usuario ou arvore foi alterado.')
print(f'[BACKUP] {BACKUP.parent.parent.parent}')
print('\nReinicie o servidor e pressione Ctrl + F5.')
