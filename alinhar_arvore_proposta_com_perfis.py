from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path.cwd().resolve()
T = ROOT / 'app' / 'templates'
S = ROOT / 'app' / 'static'
NEW = T / 'proposal_new.html'
EDIT = T / 'proposal_edit.html'
JS = S / 'proposals.js'
CSS = S / 'proposals.css'
FILES = [NEW, EDIT, JS, CSS]

missing = [str(path) for path in FILES if not path.exists()]
if missing:
    raise SystemExit('ERRO: arquivos ausentes; nada foi alterado: ' + ', '.join(missing))

backup = ROOT / f"backup_arvore_padrao_perfis_{datetime.now():%Y%m%d_%H%M%S}"
for source in FILES:
    target = backup / source.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

TREE = r'''<section class="profile-access-editor" data-access-editor>
  <div class="profile-tree-toolbar">
    <div class="profile-view-buttons">
      <button type="button" class="view-button active">Árvore de acessos</button>
      <button type="button" class="view-button" data-only-selected-button>Somente selecionados</button>
    </div>
    <input type="search" data-tree-search placeholder="Pesquisar caminho, tela ou botão">
  </div>

  <div class="profile-tree-grid">
    <section class="profile-tree-column">
      <header class="profile-column-title">Opções do Menu</header>
      <div class="profile-tree-scroll">
        {% set ns = namespace(path='', screen='', path_open=false) %}
        {% for a in accesses %}
          {% if ns.path != a.caminho_completo %}
            {% if ns.path_open %}</div></details>{% endif %}
            <details open class="profile-path-node" data-path-node>
              <summary>
                <span class="tree-expander">−</span>
                <span class="tree-folder">📁</span>
                <span>{{ a.caminho_completo }}</span>
              </summary>
              <div class="profile-screen-list">
            {% set ns.path = a.caminho_completo %}
            {% set ns.screen = '' %}
            {% set ns.path_open = true %}
          {% endif %}

          {% if ns.screen != a.tela_final %}
            <button
              type="button"
              class="profile-screen-row"
              data-screen-key="{{ a.caminho_completo }}||{{ a.tela_final }}"
              data-search="{{ (a.caminho_completo ~ ' ' ~ a.tela_final)|lower }}"
            >
              <span class="screen-access-state denied" data-screen-state>×</span>
              <span class="screen-name">{{ a.tela_final }}</span>
              <span class="screen-count" data-screen-count>0</span>
            </button>
            {% set ns.screen = a.tela_final %}
          {% endif %}
        {% endfor %}
        {% if ns.path_open %}</div></details>{% endif %}
      </div>
    </section>

    <section class="profile-buttons-column">
      <header class="profile-column-title" data-access-title>Selecione uma tela</header>
      <div class="profile-buttons-scroll">
        <p class="profile-access-hint" data-access-hint>
          Clique em uma tela à esquerda. Depois marque ou desmarque os botões desta tela.
        </p>

        {% set ns = namespace(path='', screen='', open=false) %}
        {% for a in accesses %}
          {% if ns.path != a.caminho_completo or ns.screen != a.tela_final %}
            {% if ns.open %}</div>{% endif %}
            <div
              class="profile-button-group"
              data-button-group="{{ a.caminho_completo }}||{{ a.tela_final }}"
              hidden
            >
              <button type="button" class="profile-select-screen" data-select-screen>
                <span data-select-screen-icon>×</span>
                <span data-select-screen-text>Permitir tela e todos os botões</span>
              </button>
            {% set ns.path = a.caminho_completo %}
            {% set ns.screen = a.tela_final %}
            {% set ns.open = true %}
          {% endif %}

          <label class="profile-button-row">
            <input
              type="checkbox"
              name="access_ids"
              value="{{ a.id }}"
              data-access-id="{{ a.id }}"
              {% if selected is defined and a.id in selected %}checked{% endif %}
            >
            <span class="button-access-state" data-button-state>×</span>
            <span class="button-name">{{ a.botao }}</span>
            <span class="permission-badge" data-permission-badge>Negado</span>
          </label>
        {% endfor %}
        {% if ns.open %}</div>{% endif %}
      </div>
    </section>
  </div>
</section>'''

NEW_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}Nova proposta | Gestão de Acessos{% endblock %}
{% block head %}<link rel="stylesheet" href="{{ url_for('static', path='/proposals.css') }}">{% endblock %}
{% block content %}
<a class="back" href="/portal/propostas">Voltar</a>
<section class="hero compact">
  <p class="eyebrow">Solicitação de acesso</p>
  <h1>Nova proposta</h1>
  <p>Escolha a base e ajuste as telas e os botões antes de criar.</p>
</section>
<form method="post" id="proposalCreateForm" class="proposal-workspace">
  <input type="hidden" name="access_selection_present" value="1">
  <section class="form-card proposal-meta-grid">
    <label>Nome<input name="name" required maxlength="180"></label>
    <label>Departamento<select name="department_id" required>{% for d in departments %}<option value="{{ d.id }}">{{ d.nome }}</option>{% endfor %}</select></label>
    <label>Base da proposta<select name="origin" id="origin" required><option value="COPIADO_DE_PERFIL">Copiar perfil</option><option value="CONSOLIDADO_FUNCIONARIO">Consolidado de funcionário</option></select></label>
    <label data-source="profile">Perfil base<select name="source_profile_id" id="sourceProfile" required><option value="">Selecione o perfil</option>{% for p in profiles %}<option value="{{ p.id }}">{{ p.nome }}</option>{% endfor %}</select></label>
    <label data-source="employee" class="hidden-source">Funcionário base<select name="source_employee_id" id="sourceEmployee"><option value="">Selecione o funcionário</option>{% for e in employees %}<option value="{{ e.id }}">{{ e.nome }}</option>{% endfor %}</select></label>
    <label class="span-2">Descrição<textarea name="description"></textarea></label>
    <label class="span-2">Justificativa<textarea name="justification"></textarea></label>
  </section>
  <div id="baseNote" class="proposal-base-note">Selecione o perfil. Somente os acessos permitidos começarão marcados.</div>
  __TREE__
  <div class="proposal-save"><button type="submit">Criar proposta</button></div>
</form>
{% endblock %}
{% block scripts %}<script src="{{ url_for('static', path='/proposals.js') }}"></script>{% endblock %}'''.replace('__TREE__', TREE)

EDIT_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}Editar proposta | Gestão de Acessos{% endblock %}
{% block head %}<link rel="stylesheet" href="{{ url_for('static', path='/proposals.css') }}">{% endblock %}
{% block content %}
<a class="back" href="/portal/propostas/{{ proposal.id }}">Voltar</a>
<section class="hero compact">
  <p class="eyebrow">Solicitação de acesso</p>
  <h1>Editar proposta</h1>
  <p>O símbolo da tela fica verde quando existe algum botão permitido.</p>
</section>
<form method="post" class="proposal-workspace">
  <section class="form-card proposal-meta-grid">
    <label>Nome<input name="name" required value="{{ proposal.name }}"></label>
    <label>Departamento<input value="{{ proposal.department.nome }}" disabled></label>
    <label class="span-2">Descrição<textarea name="description">{{ proposal.description or '' }}</textarea></label>
    <label class="span-2">Justificativa<textarea name="justification">{{ proposal.justification or '' }}</textarea></label>
  </section>
  __TREE__
  <div class="proposal-save"><button type="submit">Salvar alterações</button></div>
</form>
{% endblock %}
{% block scripts %}<script src="{{ url_for('static', path='/proposals.js') }}"></script>{% endblock %}'''.replace('__TREE__', TREE)

JS_TEXT = r'''(() => {
  const one = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];

  all('[data-delete]').forEach(button => button.addEventListener('click', () => {
    const dialog = one('#deleteDialog');
    if (!dialog) return;
    one('#deleteForm').action = `/portal/propostas/${button.dataset.delete}/excluir`;
    one('#deleteText').textContent = `Deseja excluir “${button.dataset.name}”?`;
    dialog.showModal();
  }));
  all('[data-close]').forEach(button => button.onclick = () => button.closest('dialog').close());

  const origin = one('#origin');
  const profile = one('#sourceProfile');
  const employee = one('#sourceEmployee');
  const note = one('#baseNote');

  function updateSourceFields() {
    if (!origin) return;
    const profileMode = origin.value === 'COPIADO_DE_PERFIL';
    profile?.closest('[data-source]')?.classList.toggle('hidden-source', !profileMode);
    employee?.closest('[data-source]')?.classList.toggle('hidden-source', profileMode);
    if (profile) { profile.required = profileMode; if (!profileMode) profile.value = ''; }
    if (employee) { employee.required = !profileMode; if (profileMode) employee.value = ''; }
    if (note) note.textContent = profileMode
      ? 'Selecione o perfil. Somente os acessos permitidos começarão marcados.'
      : 'Selecione o funcionário. Somente os acessos consolidados permitidos começarão marcados.';
  }

  const groupFor = key => one(`.profile-button-group[data-button-group="${CSS.escape(key)}"]`);
  const screenFor = key => one(`.profile-screen-row[data-screen-key="${CSS.escape(key)}"]`);
  const accessChecks = key => all('input[name="access_ids"]', groupFor(key));

  function updateButtonRow(input) {
    const row = input.closest('.profile-button-row');
    one('[data-button-state]', row).textContent = input.checked ? '✓' : '×';
    one('[data-button-state]', row).classList.toggle('allowed', input.checked);
    const badge = one('[data-permission-badge]', row);
    badge.textContent = input.checked ? 'Permitido' : 'Negado';
    badge.classList.toggle('allowed', input.checked);
  }

  function updateScreen(key) {
    const screen = screenFor(key);
    const group = groupFor(key);
    if (!screen || !group) return;
    const checks = accessChecks(key);
    const allowed = checks.filter(input => input.checked).length;
    const state = one('[data-screen-state]', screen);
    const count = one('[data-screen-count]', screen);
    state.textContent = allowed > 0 ? '✓' : '×';
    state.classList.toggle('allowed', allowed > 0);
    screen.classList.toggle('has-access', allowed > 0);
    count.textContent = allowed;
    count.hidden = allowed === 0;
    const selectIcon = one('[data-select-screen-icon]', group);
    const selectText = one('[data-select-screen-text]', group);
    selectIcon.textContent = allowed > 0 ? '✓' : '×';
    selectIcon.classList.toggle('allowed', allowed > 0);
    selectText.textContent = allowed === checks.length && checks.length
      ? 'Negar tela e todos os botões'
      : 'Permitir tela e todos os botões';
  }

  function synchronize() {
    all('input[name="access_ids"]').forEach(updateButtonRow);
    all('.profile-screen-row').forEach(screen => updateScreen(screen.dataset.screenKey));
  }

  function activateScreen(screen) {
    const key = screen.dataset.screenKey;
    all('.profile-screen-row').forEach(item => item.classList.remove('active'));
    screen.classList.add('active');
    all('.profile-button-group').forEach(group => group.hidden = true);
    const group = groupFor(key);
    if (group) group.hidden = false;
    one('[data-access-title]').textContent = key.split('||').pop();
    one('[data-access-hint]').hidden = true;
  }

  all('.profile-screen-row').forEach(screen => screen.addEventListener('click', () => activateScreen(screen)));

  all('[data-select-screen]').forEach(button => button.addEventListener('click', () => {
    const group = button.closest('.profile-button-group');
    const key = group.dataset.buttonGroup;
    const checks = accessChecks(key);
    const allow = !checks.every(input => input.checked);
    checks.forEach(input => input.checked = allow);
    synchronize();
  }));

  all('input[name="access_ids"]').forEach(input => input.addEventListener('change', synchronize));

  const search = one('[data-tree-search]');
  const onlyButton = one('[data-only-selected-button]');
  let onlySelected = false;
  function filterTree() {
    const term = (search?.value || '').toLowerCase();
    all('.profile-screen-row').forEach(screen => {
      const key = screen.dataset.screenKey;
      const hasAccess = accessChecks(key).some(input => input.checked);
      screen.hidden = !screen.dataset.search.includes(term) || (onlySelected && !hasAccess);
    });
    all('[data-path-node]').forEach(path => {
      path.hidden = all('.profile-screen-row', path).every(screen => screen.hidden);
    });
  }
  search?.addEventListener('input', filterTree);
  onlyButton?.addEventListener('click', () => {
    onlySelected = !onlySelected;
    onlyButton.classList.toggle('active', onlySelected);
    filterTree();
  });

  async function loadBase() {
    if (!origin) return;
    const source = origin.value === 'COPIADO_DE_PERFIL' ? profile : employee;
    if (!source?.value) return;
    if (note) note.textContent = 'Carregando acessos da base...';
    try {
      const response = await fetch(`/portal/propostas/base-acessos?origin=${encodeURIComponent(origin.value)}&source_id=${encodeURIComponent(source.value)}`);
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      const ids = new Set(data.access_ids.map(String));
      all('input[name="access_ids"]').forEach(input => input.checked = ids.has(input.value));
      synchronize();
      filterTree();
      if (note) note.textContent = `${ids.size} acesso(s) carregado(s). Clique em uma tela para ajustar os botões.`;
    } catch (error) {
      if (note) note.textContent = 'Não foi possível carregar os acessos da base.';
      console.error(error);
    }
  }

  origin?.addEventListener('change', () => {
    updateSourceFields();
    all('input[name="access_ids"]').forEach(input => input.checked = false);
    synchronize();
  });
  profile?.addEventListener('change', loadBase);
  employee?.addEventListener('change', loadBase);

  updateSourceFields();
  synchronize();
  const firstSelected = all('.profile-screen-row').find(screen => accessChecks(screen.dataset.screenKey).some(input => input.checked));
  if (firstSelected) activateScreen(firstSelected);
})();'''

CSS_TEXT = r'''.proposal-workspace{display:grid;gap:16px}.proposal-meta-grid{max-width:none!important;grid-template-columns:1fr 1fr!important}.span-2{grid-column:1/-1}.hidden-source{display:none!important}.proposal-base-note{padding:11px 13px;background:#eef5ff;border-left:4px solid #1f4e78;border-radius:6px;color:#27415e}.profile-access-editor{display:grid;gap:10px}.profile-tree-toolbar{display:flex;justify-content:space-between;gap:14px;align-items:center}.profile-view-buttons{display:flex;gap:6px}.view-button{background:#fff;color:#17365d;border:1px solid #9fb4c8;border-radius:5px;padding:8px 12px}.view-button.active{background:#e5f0fb;border-color:#4c94d6}.profile-tree-toolbar>input{width:min(420px,46%);padding:9px;border:1px solid #aebdca;border-radius:5px}.profile-tree-grid{display:grid;grid-template-columns:minmax(520px,1.55fr) minmax(340px,.95fr);border:1px solid #cbd5e1;background:#fff;min-height:570px}.profile-tree-column{border-right:1px solid #cbd5e1;min-width:0}.profile-column-title{font-weight:700;padding:9px 10px;border-bottom:1px solid #cbd5e1;background:#f8fafc}.profile-tree-scroll,.profile-buttons-scroll{height:570px;overflow:auto;padding:8px}.profile-path-node{padding:2px 0}.profile-path-node>summary{list-style:none;display:flex;align-items:center;gap:6px;padding:5px;cursor:pointer}.profile-path-node>summary::-webkit-details-marker{display:none}.tree-expander{display:inline-grid;place-items:center;width:14px;height:14px;border:1px solid #8b98a5;font-size:11px}.tree-folder{font-size:15px}.profile-screen-list{margin-left:18px;padding-left:14px;border-left:1px dotted #9aa8b6}.profile-screen-row{width:100%;display:grid;grid-template-columns:24px 1fr 34px;align-items:center;gap:4px;border:0;background:transparent;color:#172033;text-align:left;padding:7px 8px;border-radius:4px;cursor:pointer}.profile-screen-row:hover,.profile-screen-row.active{background:#dcecff}.screen-access-state{font-size:22px;font-weight:700;color:#e12b25;line-height:1}.screen-access-state.allowed{color:#00a33c}.screen-count{text-align:right;color:#64748b;font-size:12px}.profile-access-hint{padding:12px;color:#65758b}.profile-button-group{display:grid}.profile-select-screen{display:flex;align-items:center;gap:9px;border:0;border-bottom:1px solid #dfe5eb;background:#f8fafc;color:#172033;text-align:left;padding:10px;cursor:pointer;font-weight:700}.profile-select-screen [data-select-screen-icon]{font-size:22px;color:#e12b25}.profile-select-screen [data-select-screen-icon].allowed{color:#00a33c}.profile-button-row{display:grid;grid-template-columns:18px 25px 1fr auto;align-items:center;gap:4px;padding:7px 5px;border-bottom:1px solid #edf0f2}.button-access-state{font-size:22px;font-weight:700;color:#e12b25}.button-access-state.allowed{color:#00a33c}.permission-badge{padding:3px 8px;border-radius:999px;background:#ffe4dc;color:#a52c1f;font-size:12px}.permission-badge.allowed{background:#d5f8df;color:#06752d}.proposal-save{position:sticky;bottom:0;z-index:4;background:#fff;border-top:1px solid #d7e0e8;padding:12px;text-align:right}@media(max-width:900px){.proposal-meta-grid,.profile-tree-grid{grid-template-columns:1fr!important}.span-2{grid-column:auto}.profile-tree-column{border-right:0;border-bottom:1px solid #cbd5e1}.profile-tree-toolbar{align-items:stretch;flex-direction:column}.profile-tree-toolbar>input{width:100%}}'''

try:
    NEW.write_text(NEW_TEMPLATE, encoding='utf-8', newline='\n')
    EDIT.write_text(EDIT_TEMPLATE, encoding='utf-8', newline='\n')
    JS.write_text(JS_TEXT, encoding='utf-8', newline='\n')
    CSS.write_text(CSS_TEXT, encoding='utf-8', newline='\n')
except Exception as exc:
    for source in FILES:
        shutil.copy2(backup / source.relative_to(ROOT), source)
    raise SystemExit(f'ERRO: alteração cancelada e arquivos restaurados: {exc}')

print('Árvore de propostas alinhada ao padrão visual de Perfis.')
print('- A esquerda: tela única com V verde ou X vermelho.')
print('- A direita: somente os botões da tela ativa.')
print('- O botão Permitir tela marca todos os botões; cada botão também pode ser alterado individualmente.')
print('Backup:', backup)
