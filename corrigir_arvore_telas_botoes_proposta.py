from pathlib import Path
from datetime import datetime
import shutil

ROOT=Path.cwd().resolve(); T=ROOT/'app'/'templates'; S=ROOT/'app'/'static'
NEW=T/'proposal_new.html'; EDIT=T/'proposal_edit.html'; JS=S/'proposals.js'; CSS=S/'proposals.css'
files=[NEW,EDIT,JS,CSS]
missing=[str(p) for p in files if not p.exists()]
if missing: raise SystemExit('ERRO: arquivos ausentes; nada alterado: '+', '.join(missing))
backup=ROOT/f"backup_arvore_telas_botoes_{datetime.now():%Y%m%d_%H%M%S}"
for p in files:
 d=backup/p.relative_to(ROOT); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,d)

TREE='''<section class="dealer-editor" data-access-editor>
  <fieldset class="dealer-tree-panel">
    <legend>Opções do menu</legend>
    <div class="dealer-toolbar">
      <input type="search" data-tree-search placeholder="Pesquisar caminho ou tela">
      <label><input type="checkbox" data-only-selected> Somente selecionados</label>
    </div>
    <div class="dealer-tree">
      {% set ns=namespace(path='', screen='', path_open=false) %}
      {% for a in accesses %}
        {% if ns.path != a.caminho_completo %}
          {% if ns.path_open %}</div></details>{% endif %}
          <details open class="dealer-path" data-path>
            <summary><span class="folder-icon">▣</span><label><input type="checkbox" data-path-check> {{ a.caminho_completo }}</label></summary>
            <div class="dealer-path-children">
          {% set ns.path=a.caminho_completo %}{% set ns.screen='' %}{% set ns.path_open=true %}
        {% endif %}
        {% if ns.screen != a.tela_final %}
          <button type="button" class="dealer-screen" data-screen-key="{{ a.caminho_completo }}||{{ a.tela_final }}" data-search="{{ (a.caminho_completo ~ ' ' ~ a.tela_final)|lower }}">
            <input type="checkbox" data-screen-check aria-label="Selecionar tela {{ a.tela_final }}">
            <span class="screen-state" aria-hidden="true">×</span>
            <span>{{ a.tela_final }}</span>
          </button>
          {% set ns.screen=a.tela_final %}
        {% endif %}
      {% endfor %}
      {% if ns.path_open %}</div></details>{% endif %}
    </div>
  </fieldset>

  <fieldset class="dealer-access-panel">
    <legend>Acessos</legend>
    <h2 data-access-title>Selecione uma tela</h2>
    <p class="dealer-hint" data-access-hint>Clique no nome de uma tela à esquerda para configurar os botões.</p>
    <div class="dealer-button-groups">
      {% set ns=namespace(path='', screen='', open=false) %}
      {% for a in accesses %}
        {% if ns.path != a.caminho_completo or ns.screen != a.tela_final %}
          {% if ns.open %}</div>{% endif %}
          <div class="dealer-button-group" data-button-group="{{ a.caminho_completo }}||{{ a.tela_final }}" hidden>
            <label class="dealer-all-buttons"><input type="checkbox" data-all-buttons> Marcar todos os botões</label>
          {% set ns.path=a.caminho_completo %}{% set ns.screen=a.tela_final %}{% set ns.open=true %}
        {% endif %}
        <label class="dealer-button-option">
          <input type="checkbox" name="access_ids" value="{{ a.id }}" data-access-id="{{ a.id }}" {% if selected is defined and a.id in selected %}checked{% endif %}>
          <span>{{ a.botao }}</span>
        </label>
      {% endfor %}
      {% if ns.open %}</div>{% endif %}
    </div>
  </fieldset>
</section>'''

NEW_HTML='''{% extends "base.html" %}
{% block title %}Nova proposta | Gestão de Acessos{% endblock %}
{% block head %}<link rel="stylesheet" href="{{ url_for('static', path='/proposals.css') }}">{% endblock %}
{% block content %}
<a class="back" href="/portal/propostas">Voltar</a>
<section class="hero compact"><p class="eyebrow">Solicitação de acesso</p><h1>Nova proposta</h1><p>Escolha a base, revise as telas e ajuste os botões antes de criar.</p></section>
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
  <div id="baseNote" class="proposal-base-note">Selecione o perfil que deseja copiar. Apenas os acessos do perfil começarão marcados.</div>
  '''+TREE+'''
  <div class="proposal-save"><button type="submit">Criar proposta</button></div>
</form>
{% endblock %}
{% block scripts %}<script src="{{ url_for('static', path='/proposals.js') }}"></script>{% endblock %}'''

EDIT_HTML='''{% extends "base.html" %}
{% block title %}Editar proposta | Gestão de Acessos{% endblock %}
{% block head %}<link rel="stylesheet" href="{{ url_for('static', path='/proposals.css') }}">{% endblock %}
{% block content %}
<a class="back" href="/portal/propostas/{{ proposal.id }}">Voltar</a>
<section class="hero compact"><p class="eyebrow">Solicitação de acesso</p><h1>Editar proposta</h1><p>Selecione telas na árvore e configure os botões no painel de acessos.</p></section>
<form method="post" class="proposal-workspace">
  <section class="form-card proposal-meta-grid">
    <label>Nome<input name="name" required value="{{ proposal.name }}"></label>
    <label>Departamento<input value="{{ proposal.department.nome }}" disabled></label>
    <label class="span-2">Descrição<textarea name="description">{{ proposal.description or '' }}</textarea></label>
    <label class="span-2">Justificativa<textarea name="justification">{{ proposal.justification or '' }}</textarea></label>
  </section>
  '''+TREE+'''
  <div class="proposal-save"><button type="submit">Salvar alterações</button></div>
</form>
{% endblock %}
{% block scripts %}<script src="{{ url_for('static', path='/proposals.js') }}"></script>{% endblock %}'''

JS_TEXT=r'''(()=>{
const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
qa('[data-delete]').forEach(b=>b.addEventListener('click',()=>{const d=q('#deleteDialog');if(!d)return;q('#deleteForm').action=`/portal/propostas/${b.dataset.delete}/excluir`;q('#deleteText').textContent=`Deseja excluir “${b.dataset.name}”?`;d.showModal()}));
qa('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
const origin=q('#origin'),profile=q('#sourceProfile'),employee=q('#sourceEmployee'),note=q('#baseNote');
function sourceFields(){if(!origin)return;const isProfile=origin.value==='COPIADO_DE_PERFIL';const p=profile?.closest('[data-source]'),e=employee?.closest('[data-source]');p?.classList.toggle('hidden-source',!isProfile);e?.classList.toggle('hidden-source',isProfile);if(profile){profile.required=isProfile;if(!isProfile)profile.value=''}if(employee){employee.required=!isProfile;if(isProfile)employee.value=''}if(note)note.textContent=isProfile?'Selecione o perfil que deseja copiar. Apenas os acessos do perfil começarão marcados.':'Selecione o funcionário. Apenas os acessos consolidados começarão marcados.'}
origin?.addEventListener('change',()=>{sourceFields();clearAll();syncAll()});sourceFields();
function buttonsFor(key){return qa(`.dealer-button-group[data-button-group="${CSS.escape(key)}"] input[name="access_ids"]`)}
function screenButton(key){return q(`.dealer-screen[data-screen-key="${CSS.escape(key)}"]`)}
function syncScreen(key){const row=screenButton(key);if(!row)return;const boxes=buttonsFor(key),check=q('[data-screen-check]',row),state=q('.screen-state',row),count=boxes.filter(x=>x.checked).length;check.checked=boxes.length>0&&count===boxes.length;check.indeterminate=count>0&&count<boxes.length;row.classList.toggle('is-selected',count>0);state.textContent=count>0?'✓':'×';state.classList.toggle('is-on',count>0);const all=q('[data-all-buttons]',q(`.dealer-button-group[data-button-group="${CSS.escape(key)}"]`));if(all){all.checked=check.checked;all.indeterminate=check.indeterminate}}
function syncPaths(){qa('[data-path]').forEach(path=>{const screens=qa('[data-screen-check]',path),check=q('[data-path-check]',path),active=screens.filter(x=>x.checked||x.indeterminate).length;check.checked=screens.length>0&&screens.every(x=>x.checked);check.indeterminate=active>0&&!check.checked})}
function syncAll(){qa('.dealer-screen').forEach(r=>syncScreen(r.dataset.screenKey));syncPaths()}
function clearAll(){qa('input[name="access_ids"]').forEach(x=>x.checked=false)}
qa('.dealer-screen').forEach(row=>{const key=row.dataset.screenKey,screenCheck=q('[data-screen-check]',row);row.addEventListener('click',e=>{if(e.target===screenCheck){buttonsFor(key).forEach(x=>x.checked=screenCheck.checked);syncAll();return}qa('.dealer-screen').forEach(x=>x.classList.remove('is-active'));row.classList.add('is-active');qa('.dealer-button-group').forEach(x=>x.hidden=true);const group=q(`.dealer-button-group[data-button-group="${CSS.escape(key)}"]`);if(group)group.hidden=false;q('[data-access-title]').textContent=key.split('||').pop();q('[data-access-hint]').hidden=true});});
qa('[data-path-check]').forEach(check=>check.addEventListener('change',()=>{qa('.dealer-screen',check.closest('[data-path]')).forEach(row=>buttonsFor(row.dataset.screenKey).forEach(x=>x.checked=check.checked));syncAll()}));
qa('[data-all-buttons]').forEach(check=>check.addEventListener('change',()=>{qa('input[name="access_ids"]',check.closest('.dealer-button-group')).forEach(x=>x.checked=check.checked);syncAll()}));
qa('input[name="access_ids"]').forEach(x=>x.addEventListener('change',syncAll));
const search=q('[data-tree-search]'),only=q('[data-only-selected]');function filter(){const term=(search?.value||'').toLowerCase();qa('.dealer-screen').forEach(row=>{const selected=q('[data-screen-check]',row).checked||q('[data-screen-check]',row).indeterminate;row.hidden=!row.dataset.search.includes(term)||(only?.checked&&!selected)});qa('[data-path]').forEach(path=>path.hidden=qa('.dealer-screen',path).every(x=>x.hidden))}search?.addEventListener('input',filter);only?.addEventListener('change',filter);
async function loadBase(){if(!origin)return;const source=origin.value==='COPIADO_DE_PERFIL'?profile:employee;if(!source?.value){clearAll();syncAll();return}if(note)note.textContent='Carregando acessos da base...';try{const r=await fetch(`/portal/propostas/base-acessos?origin=${encodeURIComponent(origin.value)}&source_id=${encodeURIComponent(source.value)}`);if(!r.ok)throw new Error(await r.text());const data=await r.json(),ids=new Set(data.access_ids.map(String));qa('input[name="access_ids"]').forEach(x=>x.checked=ids.has(x.value));syncAll();if(note)note.textContent=`${ids.size} acesso(s) carregado(s). Selecione telas ou ajuste botões antes de criar.`}catch(err){if(note)note.textContent='Não foi possível carregar os acessos da base.';console.error(err)}}
profile?.addEventListener('change',loadBase);employee?.addEventListener('change',loadBase);syncAll();
})();'''

CSS_TEXT='''.proposal-workspace{display:grid;gap:16px}.proposal-meta-grid{max-width:none!important;grid-template-columns:1fr 1fr!important}.span-2{grid-column:1/-1}.hidden-source{display:none!important}.proposal-base-note{padding:11px 13px;background:#eef5ff;border-left:4px solid #1f4e78;border-radius:6px;color:#27415e}.dealer-editor{display:grid;grid-template-columns:minmax(520px,1fr) minmax(300px,.48fr);gap:14px;min-height:540px}.dealer-tree-panel,.dealer-access-panel{min-width:0;background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:10px 14px}.dealer-tree-panel legend,.dealer-access-panel legend{padding:0 7px;font-weight:700;color:#17365d}.dealer-toolbar{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;margin:5px 0 12px}.dealer-toolbar input[type="search"]{width:100%;padding:10px;border:1px solid #aebdca;border-radius:6px}.dealer-toolbar label{display:flex;align-items:center;gap:7px;white-space:nowrap}.dealer-tree{max-height:620px;overflow:auto;padding-right:6px}.dealer-path{padding:4px 0}.dealer-path>summary{list-style:none;display:flex;align-items:center;gap:6px;font-weight:700;cursor:pointer;padding:6px}.dealer-path>summary::-webkit-details-marker{display:none}.dealer-path>summary:before{content:'▾';width:14px}.dealer-path:not([open])>summary:before{content:'▸'}.dealer-path summary label{display:flex;align-items:center;gap:7px;cursor:pointer}.folder-icon{color:#d89b00}.dealer-path-children{margin-left:22px;border-left:1px dotted #9aa8b6;padding-left:10px}.dealer-screen{width:100%;display:flex;align-items:center;gap:8px;border:0;border-radius:4px;background:transparent;color:#172033;text-align:left;padding:7px 8px;cursor:pointer}.dealer-screen:hover,.dealer-screen.is-active{background:#eaf3fb}.dealer-screen input{margin:0}.screen-state{font-size:18px;font-weight:800;color:#a12b25;line-height:1}.screen-state.is-on{color:#16823a}.dealer-access-panel{align-self:start;position:sticky;top:12px}.dealer-access-panel h2{margin:6px 0 8px}.dealer-hint{color:#65758b}.dealer-button-group{display:grid;gap:4px}.dealer-all-buttons{font-weight:700;border-bottom:1px solid #e5e9ee;margin-bottom:6px;padding-bottom:9px}.dealer-button-option,.dealer-all-buttons{display:flex;align-items:center;gap:8px;padding:7px 4px}.proposal-save{position:sticky;bottom:0;z-index:4;background:#fff;border-top:1px solid #d7e0e8;padding:12px;text-align:right}@media(max-width:900px){.dealer-editor,.proposal-meta-grid{grid-template-columns:1fr!important}.span-2{grid-column:auto}.dealer-access-panel{position:static}.dealer-toolbar{grid-template-columns:1fr}}'''
try:
 NEW.write_text(NEW_HTML,encoding='utf-8',newline='\n'); EDIT.write_text(EDIT_HTML,encoding='utf-8',newline='\n'); JS.write_text(JS_TEXT,encoding='utf-8',newline='\n'); CSS.write_text(CSS_TEXT,encoding='utf-8',newline='\n')
except Exception as exc:
 for p in files: shutil.copy2(backup/p.relative_to(ROOT),p)
 raise SystemExit(f'ERRO: alteração cancelada e arquivos restaurados: {exc}')
print('Árvore de telas e painel de botões corrigidos.')
print('- A árvore mostra uma linha por tela, sem repetir a tela para cada botão.')
print('- O checkbox da tela seleciona ou remove todos os botões daquela tela.')
print('- O painel direito permite ajustar os botões individualmente.')
print('- Perfil ou funcionário base carrega somente os acessos já marcados.')
print('Backup:',backup)
