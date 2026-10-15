from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
BASE = ROOT / "app" / "templates" / "base.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_menu_departamentos_{STAMP}" / "app" / "templates" / "base.html"

if not BASE.is_file():
    raise RuntimeError(f"Arquivo nao encontrado: {BASE}")

html = BASE.read_text(encoding="utf-8-sig")

# Remove ocorrencias antigas para impedir item duplicado ou fora da posicao.
for link in (
    '<a href="/portal/departamentos">Departamentos</a>',
    '<a href="/admin/departamentos">Departamentos</a>',
):
    html = html.replace(link, "")

# O item deve ficar imediatamente depois de Perfis no menu principal.
anchors = (
    '<a href="/portal/perfis">Perfis</a>',
    '<a href="/perfis">Perfis</a>',
)
anchor = next((item for item in anchors if item in html), None)
if not anchor:
    raise RuntimeError("O link Perfis nao foi encontrado em base.html. Nenhum arquivo foi alterado.")

novo_menu = anchor + '\n        <a href="/portal/departamentos">Departamentos</a>'
html = html.replace(anchor, novo_menu, 1)

if html.count('<a href="/portal/departamentos">Departamentos</a>') != 1:
    raise RuntimeError("A validacao do menu falhou. Nenhum arquivo foi alterado.")

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(BASE, BACKUP)
BASE.write_text(html, encoding="utf-8", newline="\n")

print("\n[SUCESSO] Menu corrigido.")
print("[OK] Departamentos voltou ao menu principal.")
print("[OK] Posicionado imediatamente ao lado direito de Perfis.")
print("[OK] Link configurado para /portal/departamentos.")
print("[OK] Nenhuma rota, banco, cargo ou usuario foi alterado.")
print(f"[BACKUP] {BACKUP.parent.parent.parent}")
print("\nReinicie o servidor e pressione Ctrl+F5.")
