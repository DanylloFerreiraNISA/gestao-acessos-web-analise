from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
STATIC = ROOT / "app" / "static"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_cores_arvores_{STAMP}"
MARK_START = "/* PALETA_ARVORES_USUARIOS_PERFIS_INICIO */"
MARK_END = "/* PALETA_ARVORES_USUARIOS_PERFIS_FIM */"

# PALETA NOVA. Para trocar depois, altere somente estes valores.
COR_TEXTO = "#172033"               # nomes dos caminhos, telas e botoes
COR_TITULO = "#0f2742"              # titulo Opcoes do Menu
COR_LINHAS = "#94a3b8"              # linhas pontilhadas da arvore
COR_SELECAO_FUNDO = "#dbeafe"        # item selecionado
COR_SELECAO_TEXTO = "#0f3d66"        # texto do item selecionado
COR_PERMITIDO = "#15803d"            # check de acesso permitido
COR_PASTA = "#d97706"                # icones/pastas, quando forem texto ou SVG
COR_BORDA = "#cbd5e1"                # bordas da arvore
COR_FUNDO = "#ffffff"                # fundo da arvore

if not STATIC.exists():
    raise RuntimeError(f"Pasta nao encontrada: {STATIC}")

preferred = [STATIC / "app.css", STATIC / "styles.css", STATIC / "portal.css"]
targets = [path for path in preferred if path.exists()]
if not targets:
    raise RuntimeError("Nenhum CSS principal foi encontrado. Nenhum arquivo foi alterado.")

palette = f'''\n{MARK_START}
/* Paleta compartilhada pelas arvores das telas de usuarios e perfis. */
:root {{
  --tree-ui-text: {COR_TEXTO};
  --tree-ui-title: {COR_TITULO};
  --tree-ui-line: {COR_LINHAS};
  --tree-ui-selected-bg: {COR_SELECAO_FUNDO};
  --tree-ui-selected-text: {COR_SELECAO_TEXTO};
  --tree-ui-allowed: {COR_PERMITIDO};
  --tree-ui-folder: {COR_PASTA};
  --tree-ui-border: {COR_BORDA};
  --tree-ui-bg: {COR_FUNDO};
}}

/* Estrutura geral da arvore classica. */
:is(.classic-access, .classic-tree, .access-tree, .tree, [data-classic-tree]) {{
  color: var(--tree-ui-text) !important;
  background: var(--tree-ui-bg) !important;
  border-color: var(--tree-ui-border) !important;
}}

:is(.classic-access, .classic-tree, .access-tree, .tree, [data-classic-tree])
:is(.tree-node, li, summary, label, span, strong, a) {{
  color: var(--tree-ui-text) !important;
}}

/* Cabecalhos como Opcoes do Menu e Acessos. */
:is(.classic-access, .classic-tree, .access-tree, [data-classic-tree])
:is(th, .tree-header, .classic-tree-header, h2, h3) {{
  color: var(--tree-ui-title) !important;
  border-color: var(--tree-ui-border) !important;
}}

/* Ligacoes pontilhadas. */
:is(.classic-access, .classic-tree, .access-tree, .tree, [data-classic-tree])
:is(ul, li, .tree-branch, .tree-children) {{
  border-color: var(--tree-ui-line) !important;
}}

/* Item atual selecionado. */
:is(.classic-access, .classic-tree, .access-tree, .tree, [data-classic-tree])
:is(.active, .selected, [aria-selected="true"], .tree-selected) {{
  background: var(--tree-ui-selected-bg) !important;
  color: var(--tree-ui-selected-text) !important;
}}
:is(.classic-access, .classic-tree, .access-tree, .tree, [data-classic-tree])
:is(.active, .selected, [aria-selected="true"], .tree-selected) * {{
  color: var(--tree-ui-selected-text) !important;
}}

/* Indicadores de acesso permitido. */
:is(.classic-access, .classic-tree, .access-tree, .tree, [data-classic-tree])
:is(.allowed, .permitido, .check, .checkmark, [data-status="permitido"]) {{
  color: var(--tree-ui-allowed) !important;
}}

/* Pastas feitas com icones vetoriais ou fontes. Imagens emoji permanecem originais. */
:is(.classic-access, .classic-tree, .access-tree, .tree, [data-classic-tree])
:is(.folder, .folder-icon, svg.folder, [data-icon="folder"]) {{
  color: var(--tree-ui-folder) !important;
  fill: var(--tree-ui-folder) !important;
}}
{MARK_END}\n'''

changed = []
for target in targets:
    current = target.read_text(encoding="utf-8-sig")
    if MARK_START in current and MARK_END in current:
        before = current.split(MARK_START, 1)[0].rstrip()
        after = current.split(MARK_END, 1)[1].lstrip("\r\n")
        updated = before + palette + after
    else:
        updated = current.rstrip() + "\n" + palette

    backup = BACKUP / target.relative_to(ROOT)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    target.write_text(updated, encoding="utf-8")
    changed.append(target)
    print(f"[ALTERADO] {target.relative_to(ROOT)}")

print("\n[SUCESSO] Paleta das arvores de usuarios e perfis atualizada.")
print(f"[BACKUP] {BACKUP}")
print("[CORES] Texto azul-escuro, selecao azul-claro, linhas cinza e permitido verde.")
print("[PRESERVADO] Estrutura, filtros, botoes e funcionamento das arvores.")
print("\nReinicie o servidor e pressione Ctrl + F5.")
