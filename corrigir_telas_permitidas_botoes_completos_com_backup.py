from __future__ import annotations

import ast
import py_compile
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TARGET = ROOT / "app" / "importacao_planilhas.py"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_filtro_telas_permitidas_{STAMP}" / "app" / "importacao_planilhas.py"
MARK = "FILTRO_TELAS_PERMITIDAS_BOTOES_COMPLETOS_V1"

if not TARGET.is_file():
    raise RuntimeError(f"Arquivo nao encontrado: {TARGET}")

source = TARGET.read_text(encoding="utf-8-sig")
if MARK in source:
    print("[OK] A correcao de telas permitidas ja esta instalada.")
    raise SystemExit(0)


def function_bounds(code: str, function_name: str) -> tuple[int, int]:
    tree = ast.parse(code)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == function_name
        ),
        None,
    )
    if node is None or node.end_lineno is None:
        raise RuntimeError(
            f"A funcao {function_name} nao foi encontrada. Nenhum arquivo foi alterado."
        )
    lines = code.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: node.lineno - 1])
    end = sum(len(line) for line in lines[: node.end_lineno])
    return start, end


replacement = '''# FILTRO_TELAS_PERMITIDAS_BOTOES_COMPLETOS_V1
def _import_profile_accesses(session, mapa_data, state, result):
    """
    Mostra/importa somente telas concedidas ao perfil, mas preserva todos os
    botoes dessas telas, inclusive os negados.

    A aba Botoes por cargo e lida em duas passagens em memoria:
    1. identifica as telas permitidas por perfil;
    2. sincroniza todos os registros pertencentes a essas telas.
    """
    wb = workbook(mapa_data)
    ws = find_sheet(wb, "Botões por cargo", "Botoes por cargo")
    if ws is None:
        raise RuntimeError(
            "A aba Botoes por cargo nao foi encontrada em Mapa_Geral_Acessos.xlsx."
        )

    records = []
    allowed_screens = set()
    imported_profile_keys = set()

    # Primeira passagem: entende a permissao principal da tela.
    for line, values, headers in iter_records(ws):
        profile_name = text(row_value(values, headers, "Perfil"))
        path = text(row_value(values, headers, "Caminho completo"))
        screen = text(row_value(values, headers, "Tela final"))
        button = text(row_value(values, headers, "Botão", "Botao"))
        status = _status(row_value(values, headers, "Status"))
        item_type = key(row_value(values, headers, "Tipo item"))
        button_key = key(button)

        if not profile_name or not screen:
            continue

        profile_key = _profile_identity(profile_name)
        screen_key = (profile_key, compact_key(path), compact_key(screen))
        imported_profile_keys.add(profile_key)
        records.append(
            {
                "line": line,
                "profile_name": profile_name,
                "profile_key": profile_key,
                "path": path,
                "screen": screen,
                "button": button,
                "status": status,
                "item_type": item_type,
                "screen_key": screen_key,
            }
        )

        # A planilha identifica a permissao da tela por Tipo item = Tela.
        # Tambem aceitamos a linha explicita Acesso a tela para compatibilidade.
        is_screen_permission = (
            item_type == "tela"
            or button_key in {"acesso a tela", "acesso tela"}
        )
        if is_screen_permission and status == "Permitido":
            allowed_screens.add(screen_key)

    result["telas_permitidas"] = len(allowed_screens)

    desired_pairs_by_profile = defaultdict(set)
    seen_pairs = set()

    # Segunda passagem: para telas permitidas, leva todos os botoes e statuses.
    for record in records:
        if record["screen_key"] not in allowed_screens:
            result["linhas_de_telas_sem_permissao_ignoradas"] += 1
            continue

        profile = _get_or_create_profile(
            session,
            state,
            record["profile_name"],
            result,
        )
        access = _get_or_create_access(
            session,
            state,
            record["path"],
            record["screen"],
            record["button"],
            result,
        )
        pair = (profile.id, access.id)
        desired_pairs_by_profile[profile.id].add(pair)

        if pair in seen_pairs:
            result["permissoes_repetidas_no_arquivo"] += 1
            continue
        seen_pairs.add(pair)

        link = state["profile_access_links"].get(pair)
        if link is None:
            link = PerfilAcesso(
                perfil_id=profile.id,
                acesso_id=access.id,
                status=record["status"],
            )
            session.add(link)
            state["profile_access_links"][pair] = link
            result["permissoes_criadas"] += 1
        elif link.status != record["status"]:
            link.status = record["status"]
            result["permissoes_atualizadas"] += 1
        else:
            result["permissoes_mantidas"] += 1

    # A aba Botoes por cargo representa o mapa completo dos perfis presentes.
    # Remove da arvore desses perfis telas sem permissao e registros antigos que
    # nao pertencem mais ao mapa desejado. Usuarios e vinculos com perfis ficam intactos.
    imported_profile_ids = {
        profile.id
        for profile_key, profile in state["profiles_by_name"].items()
        if profile_key in imported_profile_keys
    }
    for pair, link in list(state["profile_access_links"].items()):
        profile_id, _ = pair
        if profile_id not in imported_profile_ids:
            continue
        if pair in desired_pairs_by_profile.get(profile_id, set()):
            continue
        session.delete(link)
        state["profile_access_links"].pop(pair, None)
        result["permissoes_removidas_sem_acesso_a_tela"] += 1
'''

start, end = function_bounds(source, "_import_profile_accesses")
updated = source[:start] + replacement + source[end:]

# Validacao de sintaxe antes do backup e da escrita.
with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as temp:
    temp.write(updated)
    temp_name = temp.name
try:
    py_compile.compile(temp_name, doraise=True)
finally:
    Path(temp_name).unlink(missing_ok=True)

# Verificacao secundaria da estrutura preparada.
for required in (
    MARK,
    "allowed_screens",
    "item_type == \"tela\"",
    "permissoes_removidas_sem_acesso_a_tela",
):
    if required not in updated:
        raise RuntimeError(
            f"Validacao da correcao falhou: {required}. Nenhum arquivo foi alterado."
        )

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TARGET, BACKUP)

try:
    TARGET.write_text(updated, encoding="utf-8")
    py_compile.compile(str(TARGET), doraise=True)
except Exception:
    shutil.copy2(BACKUP, TARGET)
    raise

print("\n[SUCESSO] Filtro de telas permitidas instalado.")
print("[OK] Somente telas com permissao principal Permitido entram na arvore.")
print("[OK] Todos os botoes dessas telas sao preservados, inclusive Negados.")
print("[OK] Caminhos sem telas permitidas desaparecem automaticamente.")
print("[OK] Na proxima importacao, vinculos antigos incorretos serao removidos.")
print("[OK] Usuarios e vinculos FuncionarioPerfil nao sao removidos.")
print(f"[BACKUP] {BACKUP.parent.parent}")
print("\nReinicie o servidor e importe novamente as duas planilhas.")
