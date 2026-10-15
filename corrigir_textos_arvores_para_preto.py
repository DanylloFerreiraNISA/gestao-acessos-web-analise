from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
STATIC = ROOT / "app" / "static"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_cores_arvores_{STAMP}"
MARKER = "/* CORRECAO_GLOBAL_TEXTOS_ARVORES_PRETO_V1 */"

if not STATIC.exists():
    raise RuntimeError(f"Pasta nao encontrada: {STATIC}")

# Aplica nos dois arquivos normalmente usados pelo sistema. Se um deles nao existir,
# o atualizador procura outros CSS que contenham seletores de arvore/perfil.
preferred = [
    STATIC / "style.css",
    STATIC / "styles.css",
    STATIC / "proposal-editor.css",
]

targets = [p for p in preferred if p.exists()]
if not targets:
    for css in STATIC.rglob("*.css"):
        text = css.read_text(encoding="utf-8-sig", errors="ignore").lower()
        if any(token in text for token in ("tree", "arvore", "profile-screen", "access-tree")):
            targets.append(css)

if not targets:
    raise RuntimeError("Nenhum arquivo CSS relacionado as arvores foi encontrado. Nenhum arquivo foi alterado.")

# Somente a cor dos textos/nomes. Fundos, bordas, espacamentos e demais cores permanecem intactos.
override = r'''

/* CORRECAO_GLOBAL_TEXTOS_ARVORES_PRETO_V1 */
/* Nomes das arvores: propostas, usuarios e perfis */
:is(
  .tree,
  .access-tree,
  .permissions-tree,
  .profile-tree,
  .profile-access-editor,
  .profile-tree-column,
  .profile-tree-scroll,
  .profile-path-node,
  .profile-screen-row,
  .profile-button-group,
  .user-tree,
  .user-access-tree,
  [data-access-editor],
  [data-tree],
  [data-path-node]
) :is(
  summary,
  label,
  .tree-label,
  .tree-name,
  .tree-title,
  .tree-node-name,
  .tree-folder-name,
  .path-name,
  .screen-name,
  .button-name,
  .profile-column-title,
  .profile-screen-name,
  .profile-path-name,
  .profile-button-row,
  .profile-screen-row
) {
  color: #000000 !important;
}

/* Texto direto nos nós, sem alterar ícones ou fundos */
:is(
  .profile-path-node > summary,
  .profile-screen-row,
  .profile-button-row,
  .tree-node > summary,
  .tree-node > label,
  .access-tree details > summary,
  .permissions-tree details > summary,
  .user-access-tree details > summary
) {
  color: #000000 !important;
}
'''

changed = []
for target in dict.fromkeys(targets):
    current = target.read_text(encoding="utf-8-sig")
    if MARKER in current:
        print(f"[OK] Correcao ja existente: {target.relative_to(ROOT)}")
        continue

    backup = BACKUP / target.relative_to(ROOT)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    target.write_text(current.rstrip() + override + "\n", encoding="utf-8")
    changed.append(target)
    print(f"[ALTERADO] {target.relative_to(ROOT)}")

if not changed:
    print("\nNenhuma nova alteracao foi necessaria.")
else:
    print("\n[SUCESSO] Os nomes das arvores foram definidos como preto.")
    print(f"[BACKUP] {BACKUP}")
    print("[ESCOPO] Propostas, usuarios e perfis.")
    print("[PRESERVADO] Fundos, layout, espacamentos e demais cores nao foram alterados.")

print("\nReinicie o servidor e pressione Ctrl + F5 no navegador.")
