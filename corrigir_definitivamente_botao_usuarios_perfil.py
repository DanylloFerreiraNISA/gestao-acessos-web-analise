from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TEMPLATE = ROOT / "app" / "templates" / "perfil.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_perfil_antes_corrigir_botao_{STAMP}" / "app" / "templates" / "perfil.html"

if not TEMPLATE.exists():
    raise RuntimeError(f"Template nao encontrado: {TEMPLATE}")

# Substitui somente o template de detalhe por uma versao limpa. Isso remove as duas
# colunas verticais criadas pelas tentativas anteriores e preserva a arvore classica.
clean_template = r'''{% extends "base.html" %}
{% block title %}{{ perfil.nome }}{% endblock %}
{% block content %}
<a class="back" href="/portal/perfis">Voltar para perfis</a>

<section class="hero compact">
  <p class="eyebrow">Perfil</p>
  <h1>{{ perfil.nome }}</h1>
  <p>{{ usuarios|length }} usuarios vinculados</p>
  <p id="profile-origin-label"></p>
  <div id="proposal-profile-actions" hidden>
    <form method="post" action="/portal/perfis/{{ perfil.id }}/situacao">
      <input type="hidden" name="situacao" value="{{ 'Inativo' if perfil.situacao != 'Inativo' else 'Ativo' }}">
      <button type="submit">{{ 'Inativar perfil' if perfil.situacao != 'Inativo' else 'Reativar perfil' }}</button>
    </form>
  </div>
</section>

<div id="profile-access-view">
  <script type="application/json" id="classic-profile">{{ acessos|tojson }}</script>
  {% set source_id='classic-profile' %}
  {% set compare=false %}
  {% include '_classic_access.html' %}
</div>

<section id="profile-users-view" class="panel" hidden>
  <div class="profile-users-header">
    <div>
      <h2>Usuarios vinculados</h2>
      <p>{{ usuarios|length }} usuario(s) vinculado(s) a este perfil.</p>
    </div>
    <input type="search" id="profile-user-search" placeholder="Pesquisar usuario" aria-label="Pesquisar usuario vinculado">
  </div>

  <div class="table-responsive">
    <table class="profile-users-table">
      <thead>
        <tr><th>Nome</th><th>Login</th><th>Departamento</th><th>Situacao</th></tr>
      </thead>
      <tbody>
        {% for usuario in usuarios %}
        <tr data-profile-user-row>
          <td>{{ usuario.nome }}</td>
          <td>{{ usuario.login }}</td>
          <td>{{ usuario.departamento.nome if usuario.departamento else 'Sem departamento' }}</td>
          <td>{{ 'Ativo' if usuario.ativo else 'Inativo' }}</td>
        </tr>
        {% else %}
        <tr><td colspan="4">Nenhum usuario vinculado a este perfil.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <p id="profile-users-no-results" hidden>Nenhum usuario encontrado.</p>
</section>

<style>
#profile-users-view[hidden],#profile-access-view[hidden]{display:none!important}
.profile-users-header{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:14px}
.profile-users-header h2,.profile-users-header p{margin:0 0 4px}
.profile-users-header input{width:min(320px,100%)}
.profile-users-table{width:100%;border-collapse:collapse}
.profile-users-table th,.profile-users-table td{padding:10px;text-align:left;border-bottom:1px solid #d7e0e8;color:#000}
.profile-users-toolbar-button.active{background:#dbeafe;border-color:#60a5fa}
@media(max-width:700px){.profile-users-header{display:grid}}
</style>

<script>
document.addEventListener('DOMContentLoaded', () => {
  const accessView = document.getElementById('profile-access-view');
  const usersView = document.getElementById('profile-users-view');
  if (!accessView || !usersView) return;

  const buttons = [...accessView.querySelectorAll('button')];
  const pathsButton = buttons.find(button =>
    button.textContent.trim().toLocaleLowerCase('pt-BR').includes('somente caminhos')
  );
  const treeButton = buttons.find(button => {
    const text = button.textContent.trim().toLocaleLowerCase('pt-BR');
    return text.includes('arvore de acessos') || text.includes('árvore de acessos');
  });
  const anchor = pathsButton || treeButton;

  if (anchor && anchor.parentElement) {
    const usersButton = document.createElement('button');
    usersButton.type = 'button';
    usersButton.className = anchor.className + ' profile-users-toolbar-button';
    usersButton.textContent = 'Usuarios vinculados ({{ usuarios|length }})';
    usersButton.setAttribute('aria-expanded', 'false');
    anchor.insertAdjacentElement('afterend', usersButton);

    usersButton.addEventListener('click', () => {
      const openingUsers = usersView.hidden;
      usersView.hidden = !openingUsers;
      accessView.hidden = openingUsers;
      usersButton.classList.toggle('active', openingUsers);
      usersButton.setAttribute('aria-expanded', String(openingUsers));
    });

    // Quando um controle da arvore for clicado, volta da lista de usuarios para a arvore.
    buttons.forEach(button => button.addEventListener('click', () => {
      usersView.hidden = true;
      accessView.hidden = false;
      usersButton.classList.remove('active');
      usersButton.setAttribute('aria-expanded', 'false');
    }));
  }

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
      document.getElementById('profile-origin-label').textContent = data.generated ? 'Gerado na proposta' : 'Importado do ERP';
      if (data.generated && data.can_manage) {
        document.getElementById('proposal-profile-actions').hidden = false;
      }
    });
});
</script>
{% endblock %}
'''

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TEMPLATE, BACKUP)
TEMPLATE.write_text(clean_template, encoding="utf-8")

print("[OK] Colunas verticais antigas removidas")
print("[OK] Arvore classica mantida sem encapsulamento lateral")
print("[OK] Botao Usuarios vinculados criado ao lado de Somente caminhos")
print("[OK] Lista de usuarios abre no lugar da arvore")
print("[OK] Pesquisa de usuarios mantida")
print(f"[BACKUP] {BACKUP.parent.parent.parent}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
