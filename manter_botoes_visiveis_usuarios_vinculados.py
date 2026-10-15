from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TEMPLATE = ROOT / "app" / "templates" / "perfil.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_manter_botoes_perfil_{STAMP}" / "app" / "templates" / "perfil.html"
MARKER = "MANTER_TOOLBAR_PERFIL_VISIVEL_V1"

if not TEMPLATE.exists():
    raise RuntimeError(f"Template nao encontrado: {TEMPLATE}")

html = TEMPLATE.read_text(encoding="utf-8-sig")

if MARKER in html:
    print("[OK] A barra de botoes ja foi corrigida. Nenhum arquivo foi alterado.")
    raise SystemExit(0)

required = [
    "const anchor = pathsButton || treeButton;",
    "anchor.insertAdjacentElement('afterend', usersButton);",
    "accessView.hidden = openingUsers;",
]
missing = [item for item in required if item not in html]
if missing:
    raise RuntimeError(
        "A estrutura esperada do perfil nao foi encontrada: "
        + ", ".join(missing)
        + ". Nenhum arquivo foi alterado."
    )

# A barra com Arvore de acessos, Somente caminhos, Usuarios vinculados e pesquisa
# e retirada de dentro do painel que e ocultado. Assim, somente o conteudo abaixo
# alterna entre arvore e usuarios, enquanto os controles permanecem visiveis.
old = """    anchor.insertAdjacentElement('afterend', usersButton);

    usersButton.addEventListener('click', () => {"""
new = f"""    anchor.insertAdjacentElement('afterend', usersButton);

    // {MARKER}
    // Move a barra de controles para fora do painel que alterna entre arvore e usuarios.
    const toolbar = anchor.parentElement;
    const viewsParent = accessView.parentElement;
    if (toolbar && viewsParent) {{
      viewsParent.insertBefore(toolbar, accessView);
    }}

    usersButton.addEventListener('click', () => {{"""
if old not in html:
    raise RuntimeError("O ponto de movimentacao da barra nao foi encontrado. Nenhum arquivo foi alterado.")
html = html.replace(old, new, 1)

# Ao clicar em Arvore de acessos ou Somente caminhos, garante que a arvore volte.
# Como os botoes foram movidos para fora de accessView, eles continuam acessiveis.
old_handler = """    buttons.forEach(button => button.addEventListener('click', () => {
      usersView.hidden = true;
      accessView.hidden = false;
      usersButton.classList.remove('active');
      usersButton.setAttribute('aria-expanded', 'false');
    }));"""
new_handler = """    buttons.forEach(button => button.addEventListener('click', () => {
      usersView.hidden = true;
      accessView.hidden = false;
      usersButton.classList.remove('active');
      usersButton.setAttribute('aria-expanded', 'false');
    }));"""
# Mantem o bloco explicitamente. Esta verificacao evita alterar uma versao inesperada.
if old_handler not in html:
    raise RuntimeError("O retorno para a arvore nao foi encontrado. Nenhum arquivo foi alterado.")

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TEMPLATE, BACKUP)
TEMPLATE.write_text(html, encoding="utf-8")

print("[OK] Botoes Arvore de acessos e Somente caminhos permanecem visiveis")
print("[OK] Botao Usuarios vinculados permanece na mesma barra")
print("[OK] Campo de pesquisa da arvore permanece visivel")
print("[OK] Apenas o conteudo alterna entre arvore e usuarios")
print(f"[BACKUP] {BACKUP.parent.parent.parent}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
