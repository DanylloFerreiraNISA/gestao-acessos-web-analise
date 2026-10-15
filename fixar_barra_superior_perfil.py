from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TEMPLATE = ROOT / "app" / "templates" / "perfil.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_barra_superior_perfil_{STAMP}" / "app" / "templates" / "perfil.html"
MARKER = "BARRA_SUPERIOR_PERFIL_FIXA_V1"

if not TEMPLATE.exists():
    raise RuntimeError(f"Template nao encontrado: {TEMPLATE}")

html = TEMPLATE.read_text(encoding="utf-8-sig")
if "profile-access-view" not in html or "profile-users-view" not in html:
    raise RuntimeError("A estrutura atual do perfil nao foi encontrada. Nenhum arquivo foi alterado.")

# Remove scripts anteriores de controle inseridos pelas ultimas correcoes.
patterns = [
    r"<script>\s*document\.addEventListener\('DOMContentLoaded',\s*\(\)\s*=>\s*\{.*?profile-users-view.*?</script>",
]
for pattern in patterns:
    html = re.sub(pattern, "", html, count=1, flags=re.S)

# Remove correcoes antigas que moviam a toolbar.
html = re.sub(r"<!-- BOTAO_USUARIOS_AO_LADO_DOS_CAMINHOS_V1 -->.*?(?=<script>|{% endblock %})", "", html, flags=re.S)
html = html.replace("// MANTER_TOOLBAR_PERFIL_VISIVEL_V1", "")

script = f'''\n<!-- {MARKER} -->
<style>
.profile-mode-toolbar{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:18px 0 10px}}
.profile-mode-toolbar button{{white-space:nowrap}}
.profile-mode-toolbar button.active{{background:#dbeafe!important;border-color:#60a5fa!important}}
.profile-mode-toolbar .profile-tree-search{{margin-left:auto;min-width:280px}}
#profile-users-view[hidden],#profile-access-view[hidden]{{display:none!important}}
@media(max-width:760px){{.profile-mode-toolbar .profile-tree-search{{margin-left:0;width:100%;min-width:0}}}}
</style>
<script>
document.addEventListener('DOMContentLoaded', () => {{
  const accessView = document.getElementById('profile-access-view');
  const usersView = document.getElementById('profile-users-view');
  if (!accessView || !usersView) return;

  const normalize = value => value.trim().toLocaleLowerCase('pt-BR');
  const originalButtons = [...accessView.querySelectorAll('button')];
  const originalTree = originalButtons.find(button => {{
    const text = normalize(button.textContent);
    return text.includes('arvore de acessos') || text.includes('árvore de acessos');
  }});
  const originalPaths = originalButtons.find(button => normalize(button.textContent).includes('somente caminhos'));
  if (!originalTree || !originalPaths) return;

  const toolbar = document.createElement('div');
  toolbar.className = 'profile-mode-toolbar';

  function makeButton(text) {{
    const button = document.createElement('button');
    button.type = 'button';
    button.className = originalTree.className;
    button.textContent = text;
    return button;
  }}

  const treeButton = makeButton('Arvore de acessos');
  const pathsButton = makeButton('Somente caminhos');
  const usersButton = makeButton('Usuarios vinculados ({{{{ usuarios|length }}}})');
  toolbar.append(treeButton, pathsButton, usersButton);

  const search = [...accessView.querySelectorAll('input[type="search"], input')].find(input =>
    (input.placeholder || '').toLocaleLowerCase('pt-BR').includes('pesquisar')
  );
  if (search) {{
    search.classList.add('profile-tree-search');
    toolbar.appendChild(search);
  }}

  accessView.parentElement.insertBefore(toolbar, accessView);
  originalTree.style.display = 'none';
  originalPaths.style.display = 'none';

  function activate(button) {{
    [treeButton, pathsButton, usersButton].forEach(item => item.classList.toggle('active', item === button));
  }}

  treeButton.addEventListener('click', () => {{
    usersView.hidden = true;
    accessView.hidden = false;
    originalTree.click();
    activate(treeButton);
  }});

  pathsButton.addEventListener('click', () => {{
    usersView.hidden = true;
    accessView.hidden = false;
    originalPaths.click();
    activate(pathsButton);
  }});

  usersButton.addEventListener('click', () => {{
    accessView.hidden = true;
    usersView.hidden = false;
    activate(usersButton);
  }});

  activate(treeButton);

  const userSearch = document.getElementById('profile-user-search');
  const rows = [...document.querySelectorAll('[data-profile-user-row]')];
  const noResults = document.getElementById('profile-users-no-results');
  if (userSearch) {{
    userSearch.addEventListener('input', () => {{
      const query = userSearch.value.trim().toLocaleLowerCase('pt-BR');
      let visible = 0;
      rows.forEach(row => {{
        const show = !query || row.textContent.toLocaleLowerCase('pt-BR').includes(query);
        row.hidden = !show;
        if (show) visible += 1;
      }});
      if (noResults) noResults.hidden = visible !== 0 || rows.length === 0;
    }});
  }}

  fetch('/api/perfis/{{{{ perfil.id }}}}/origem-proposta')
    .then(response => response.ok ? response.json() : null)
    .then(data => {{
      if (!data) return;
      const label = document.getElementById('profile-origin-label');
      if (label) label.textContent = data.generated ? 'Gerado na proposta' : 'Importado do ERP';
      const actions = document.getElementById('proposal-profile-actions');
      if (actions && data.generated && data.can_manage) actions.hidden = false;
    }});
}});
</script>
'''

if MARKER in html:
    html = re.sub(rf"<!-- {MARKER} -->.*?</script>", script.strip(), html, count=1, flags=re.S)
else:
    if "{% endblock %}" not in html:
        raise RuntimeError("O final do template nao foi encontrado. Nenhum arquivo foi alterado.")
    html = html.replace("{% endblock %}", script + "{% endblock %}", 1)

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TEMPLATE, BACKUP)
TEMPLATE.write_text(html, encoding="utf-8")

print("[OK] Barra fixa criada acima do conteudo")
print("[OK] Os tres botoes permanecem no topo em todos os modos")
print("[OK] Somente caminhos aciona o botao original da arvore")
print("[OK] Destaque azul acompanha o modo selecionado")
print("[OK] Pesquisa da arvore permanece na barra superior")
print(f"[BACKUP] {BACKUP.parent.parent.parent}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
