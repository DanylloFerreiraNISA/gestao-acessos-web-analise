from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TEMPLATE = ROOT / "app" / "templates" / "perfil.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_botao_usuarios_caminhos_{STAMP}" / "app" / "templates" / "perfil.html"
MARKER = "BOTAO_USUARIOS_AO_LADO_DOS_CAMINHOS_V1"

if not TEMPLATE.exists():
    raise RuntimeError(f"Template nao encontrado: {TEMPLATE}")

html = TEMPLATE.read_text(encoding="utf-8-sig")
if "ABA_USUARIOS_VINCULADOS_PERFIL_V1" not in html:
    raise RuntimeError(
        "A estrutura de abas de usuarios vinculados nao foi encontrada em perfil.html. "
        "Nenhum arquivo foi alterado."
    )
if MARKER in html:
    print("[OK] O botao ja esta ao lado dos controles da arvore. Nenhum arquivo foi alterado.")
    raise SystemExit(0)

# Esconde a barra lateral criada anteriormente. O botao Usuarios vinculados sera movido
# por JavaScript para a mesma linha de Arvore de acessos e Somente caminhos.
style_patch = f'''\n<!-- {MARKER} -->
<style>
.profile-tab-buttons{{display:none!important}}
#panel-users{{margin-top:14px}}
.profile-users-toolbar-button{{white-space:nowrap}}
</style>
<script>
document.addEventListener('DOMContentLoaded', () => {{
  const usersButton = document.getElementById('tab-users');
  const usersPanel = document.getElementById('panel-users');
  const accessPanel = document.getElementById('panel-accesses');
  if (!usersButton || !usersPanel || !accessPanel) return;

  // Localiza a linha dos controles gerados pela arvore classica.
  const candidates = [...accessPanel.querySelectorAll('button')];
  const pathsButton = candidates.find(button =>
    button.textContent.trim().toLocaleLowerCase('pt-BR').includes('somente caminhos')
  );
  const treeButton = candidates.find(button =>
    button.textContent.trim().toLocaleLowerCase('pt-BR').includes('árvore de acessos') ||
    button.textContent.trim().toLocaleLowerCase('pt-BR').includes('arvore de acessos')
  );
  const anchor = pathsButton || treeButton;
  if (!anchor || !anchor.parentElement) return;

  usersButton.classList.add('profile-users-toolbar-button');
  usersButton.classList.remove('active');
  usersButton.removeAttribute('aria-controls');
  usersButton.setAttribute('aria-expanded', 'false');
  usersButton.textContent = `Usuários vinculados (${{document.querySelectorAll('[data-profile-user-row]').length}})`;
  anchor.insertAdjacentElement('afterend', usersButton);
  usersButton.style.display = '';

  usersButton.addEventListener('click', event => {{
    event.preventDefault();
    const opening = usersPanel.hidden;
    usersPanel.hidden = !opening;
    accessPanel.hidden = opening;
    usersButton.classList.toggle('active', opening);
    usersButton.setAttribute('aria-expanded', String(opening));
    if (!opening) {{
      const firstTreeControl = treeButton || candidates[0];
      if (firstTreeControl) firstTreeControl.focus();
    }}
  }});
}});
</script>
'''

if "{% endblock %}" not in html:
    raise RuntimeError("O final do bloco content nao foi encontrado. Nenhum arquivo foi alterado.")

html = html.replace("{% endblock %}", style_patch + "{% endblock %}", 1)

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TEMPLATE, BACKUP)
TEMPLATE.write_text(html, encoding="utf-8")

print("[OK] Barra lateral de abas removida")
print("[OK] Botao Usuarios vinculados movido para o lado de Somente caminhos")
print("[OK] Arvore classica preservada")
print("[OK] A lista de usuarios continua com pesquisa e contador")
print(f"[BACKUP] {BACKUP.parent.parent.parent}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
