from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TEMPLATE = ROOT / "app" / "templates" / "perfil.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_aba_usuarios_perfil_{STAMP}" / "app" / "templates" / "perfil.html"
MARKER = "ABA_USUARIOS_VINCULADOS_PERFIL_V1"

if not TEMPLATE.exists():
    raise RuntimeError(f"Template nao encontrado: {TEMPLATE}")

html = TEMPLATE.read_text(encoding="utf-8-sig")
if MARKER in html:
    print("[OK] A aba de usuarios vinculados ja esta instalada. Nenhum arquivo foi alterado.")
    raise SystemExit(0)

classic_block = """<script type=\"application/json\" id=\"classic-profile\">{{ acessos|tojson }}</script>
{% set source_id='classic-profile' %}
{% set compare=false %}
{% include '_classic_access.html' %}"""

if classic_block not in html:
    raise RuntimeError(
        "A arvore classica esperada nao foi encontrada em perfil.html. "
        "Nenhum arquivo foi alterado."
    )

replacement = r'''<!-- ABA_USUARIOS_VINCULADOS_PERFIL_V1 -->
<section class="profile-tabs" aria-label="Informacoes do perfil">
  <div class="profile-tab-buttons" role="tablist" aria-label="Abas do perfil">
    <button type="button" id="tab-accesses" class="profile-tab-button active" role="tab" aria-selected="true" aria-controls="panel-accesses" data-profile-tab="accesses">
      Árvore de acessos
    </button>
    <button type="button" id="tab-users" class="profile-tab-button" role="tab" aria-selected="false" aria-controls="panel-users" data-profile-tab="users">
      Usuários vinculados ({{ usuarios|length }})
    </button>
  </div>

  <div id="panel-accesses" class="profile-tab-panel" role="tabpanel" aria-labelledby="tab-accesses">
    <script type="application/json" id="classic-profile">{{ acessos|tojson }}</script>
    {% set source_id='classic-profile' %}
    {% set compare=false %}
    {% include '_classic_access.html' %}
  </div>

  <div id="panel-users" class="profile-tab-panel" role="tabpanel" aria-labelledby="tab-users" hidden>
    <section class="panel">
      <div class="profile-users-header">
        <div>
          <h2>Usuários vinculados</h2>
          <p>{{ usuarios|length }} usuário(s) vinculado(s) a este perfil.</p>
        </div>
        <input type="search" id="profile-user-search" placeholder="Pesquisar usuário" aria-label="Pesquisar usuário vinculado">
      </div>

      <div class="table-responsive">
        <table class="profile-users-table">
          <thead>
            <tr>
              <th>Nome</th>
              <th>Login</th>
              <th>Departamento</th>
              <th>Situação</th>
            </tr>
          </thead>
          <tbody id="profile-users-body">
            {% for usuario in usuarios %}
            <tr data-profile-user-row>
              <td>{{ usuario.nome }}</td>
              <td>{{ usuario.login }}</td>
              <td>{{ usuario.departamento.nome if usuario.departamento else 'Sem departamento' }}</td>
              <td>{{ 'Ativo' if usuario.ativo else 'Inativo' }}</td>
            </tr>
            {% else %}
            <tr id="profile-users-empty"><td colspan="4">Nenhum usuário está vinculado a este perfil.</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      <p id="profile-users-no-results" hidden>Nenhum usuário encontrado para a pesquisa informada.</p>
    </section>
  </div>
</section>

<style>
.profile-tab-buttons{display:flex;gap:8px;margin:18px 0 14px;border-bottom:1px solid #d7e0e8}
.profile-tab-button{border:0;background:transparent;color:#334155;padding:10px 14px;cursor:pointer;border-bottom:3px solid transparent;font-weight:600}
.profile-tab-button.active{color:#173f6b;border-bottom-color:#245b88}
.profile-tab-panel[hidden]{display:none!important}
.profile-users-header{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:14px}
.profile-users-header h2,.profile-users-header p{margin:0 0 4px}
.profile-users-header input{max-width:320px}
.profile-users-table{width:100%;border-collapse:collapse}
.profile-users-table th,.profile-users-table td{text-align:left;padding:10px;border-bottom:1px solid #e2e8f0;color:#000}
@media(max-width:700px){.profile-users-header{display:grid}.profile-users-header input{max-width:none;width:100%}.profile-tab-buttons{overflow-x:auto}}
</style>

<script>
(() => {
  const buttons = [...document.querySelectorAll('[data-profile-tab]')];
  const panels = {
    accesses: document.getElementById('panel-accesses'),
    users: document.getElementById('panel-users')
  };

  function openTab(name) {
    buttons.forEach(button => {
      const selected = button.dataset.profileTab === name;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', String(selected));
    });
    Object.entries(panels).forEach(([key, panel]) => {
      if (panel) panel.hidden = key !== name;
    });
  }

  buttons.forEach(button => button.addEventListener('click', () => openTab(button.dataset.profileTab)));

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
})();
</script>'''

updated = html.replace(classic_block, replacement, 1)
BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TEMPLATE, BACKUP)
TEMPLATE.write_text(updated, encoding="utf-8")

print("[OK] Aba Arvore de acessos preservada")
print("[OK] Aba Usuarios vinculados adicionada")
print("[OK] Contador e pesquisa de usuarios adicionados")
print("[OK] Nome, login, departamento e situacao exibidos")
print(f"[BACKUP] {BACKUP.parent.parent.parent}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
