from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TEMPLATE = ROOT / 'app' / 'templates' / 'perfil.html'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
BACKUP = ROOT / f'backup_controles_perfil_{STAMP}' / 'app' / 'templates' / 'perfil.html'

if not TEMPLATE.exists():
    raise RuntimeError(f'Template nao encontrado: {TEMPLATE}')

html = TEMPLATE.read_text(encoding='utf-8-sig')

start = html.find('<script>\ndocument.addEventListener(\'DOMContentLoaded\', () => {')
end = html.find('</script>', start)
if start < 0 or end < 0:
    raise RuntimeError('O script atual do perfil nao foi encontrado. Nenhum arquivo foi alterado.')
end += len('</script>')

new_script = r'''<script>
document.addEventListener('DOMContentLoaded', () => {
  const accessView = document.getElementById('profile-access-view');
  const usersView = document.getElementById('profile-users-view');
  if (!accessView || !usersView) return;

  const originalButtons = [...accessView.querySelectorAll('button')];
  const normalize = value => value.trim().toLocaleLowerCase('pt-BR');
  const pathsButton = originalButtons.find(button => normalize(button.textContent).includes('somente caminhos'));
  const treeButton = originalButtons.find(button => {
    const text = normalize(button.textContent);
    return text.includes('arvore de acessos') || text.includes('árvore de acessos');
  });
  const anchor = pathsButton || treeButton;
  if (!anchor || !anchor.parentElement) return;

  const toolbar = anchor.parentElement;
  const contentRoot = toolbar.parentElement;
  if (!contentRoot) return;

  const usersButton = document.createElement('button');
  usersButton.type = 'button';
  usersButton.className = anchor.className + ' profile-users-toolbar-button';
  usersButton.textContent = 'Usuarios vinculados ({{ usuarios|length }})';
  usersButton.setAttribute('aria-pressed', 'false');
  anchor.insertAdjacentElement('afterend', usersButton);

  // Mantem os controles no mesmo lugar. Apenas os paineis abaixo da barra alternam.
  const treeContent = [...contentRoot.children].filter(element => element !== toolbar);
  contentRoot.insertBefore(usersView, toolbar.nextSibling);

  function setActiveButton(activeButton) {
    [treeButton, pathsButton, usersButton].filter(Boolean).forEach(button => {
      const active = button === activeButton;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }

  function showTree(activeButton) {
    usersView.hidden = true;
    treeContent.forEach(element => { element.hidden = false; });
    setActiveButton(activeButton || treeButton);
  }

  function showUsers() {
    treeContent.forEach(element => { element.hidden = true; });
    usersView.hidden = false;
    setActiveButton(usersButton);
  }

  // Os listeners originais continuam funcionando, pois os botoes nao saem do container.
  if (treeButton) treeButton.addEventListener('click', () => showTree(treeButton));
  if (pathsButton) pathsButton.addEventListener('click', () => showTree(pathsButton));
  usersButton.addEventListener('click', showUsers);

  // Corrige o destaque inicial e acompanha cliques nos modos da arvore.
  setActiveButton(treeButton || pathsButton);

  const search = document.getElementById('profile-user-search');
  const rows = [...document.querySelectorAll('[data-profile-user-row]')];
  const noResults = document.getElementById('profile-users-no-results');
  if (search) {
    search.addEventListener('input', () => {
      const query = search.value.trim().toLocaleLowerCase('pt-BR');
      let visible = 0;
      rows.forEach(row => {
        const show = !query || row.textContent.toLocaleLowerCase('pt-BR').includes(query);
        row.hidden = !show;
        if (show) visible += 1;
      });
      if (noResults) noResults.hidden = visible !== 0 || rows.length === 0;
    });
  }

  fetch('/api/perfis/{{ perfil.id }}/origem-proposta')
    .then(response => response.ok ? response.json() : null)
    .then(data => {
      if (!data) return;
      const label = document.getElementById('profile-origin-label');
      if (label) label.textContent = data.generated ? 'Gerado na proposta' : 'Importado do ERP';
      if (data.generated && data.can_manage) {
        const actions = document.getElementById('proposal-profile-actions');
        if (actions) actions.hidden = false;
      }
    });
});
</script>'''

updated = html[:start] + new_script + html[end:]

# Evita que um estilo antigo deixe somente o primeiro botao com aparencia ativa.
style_fix = '''\n<style>\n.profile-users-toolbar-button.active{background:#dbeafe!important;border-color:#60a5fa!important}\n</style>\n'''
if 'profile-users-toolbar-button.active{background:#dbeafe!important' not in updated:
    updated = updated.replace('{% endblock %}', style_fix + '{% endblock %}', 1)

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TEMPLATE, BACKUP)
TEMPLATE.write_text(updated, encoding='utf-8')

print('[OK] Somente caminhos voltou a executar no container original')
print('[OK] Barra de botoes permanece visivel ao abrir Usuarios vinculados')
print('[OK] Destaque azul acompanha Arvore, Caminhos e Usuarios')
print('[OK] Apenas o conteudo abaixo da barra e alternado')
print(f'[BACKUP] {BACKUP.parent.parent.parent}')
print('\nReinicie o servidor e pressione Ctrl + F5.')
