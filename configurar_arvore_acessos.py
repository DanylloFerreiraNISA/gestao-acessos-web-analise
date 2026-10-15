from pathlib import Path
import py_compile

ROOT = Path.cwd()
APP = ROOT / 'app'
TEMPLATES = APP / 'templates'
STATIC = APP / 'static'
MAIN = APP / 'main.py'

for path in (MAIN, TEMPLATES / 'base.html', STATIC / 'styles.css'):
    if not path.exists():
        raise SystemExit(f'Arquivo obrigatorio nao encontrado: {path}')

# JavaScript unico para montar arvore por caminho > tela > botao.
TREE_JS = r'''function statusClass(value){
  const status=String(value||'Nao identificado').toLocaleLowerCase('pt-BR');
  if(status==='permitido') return 'is-allowed';
  if(status==='negado') return 'is-denied';
  return 'is-unknown';
}
function splitPath(value){
  return String(value||'Sem modulo').split(/\s*>\s*|\s*\/\s*|\s*\\\s*/).map(x=>x.trim()).filter(Boolean);
}
function addNode(root,parts,item){
  let node=root;
  parts.forEach(part=>{node.children[part]??={children:{},items:[]};node=node.children[part]});
  node.items.push(item);
}
function renderBranch(name,node,open=false){
  const details=document.createElement('details'); details.className='access-node'; details.open=open;
  const summary=document.createElement('summary');
  const count=Object.values(node.children).reduce((n,c)=>n+countItems(c),0)+node.items.length;
  summary.innerHTML=`<span>${escapeHtml(name)}</span><small>${count}</small>`; details.appendChild(summary);
  const body=document.createElement('div'); body.className='access-branch';
  Object.entries(node.children).sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([child,content])=>body.appendChild(renderBranch(child,content,false)));
  node.items.sort((a,b)=>String(a.botao||'').localeCompare(String(b.botao||''),'pt-BR')).forEach(item=>body.appendChild(renderLeaf(item)));
  details.appendChild(body); return details;
}
function countItems(node){return node.items.length+Object.values(node.children).reduce((n,c)=>n+countItems(c),0)}
function renderLeaf(item){
  const leaf=document.createElement('article');
  leaf.className=`access-leaf ${statusClass(item.status)}`;
  const statuses=item.statusA!==undefined?`<span class="compare-status ${statusClass(item.statusA)}">${escapeHtml(item.statusA)}</span><span class="compare-arrow">→</span><span class="compare-status ${statusClass(item.statusB)}">${escapeHtml(item.statusB)}</span>`:`<span class="access-status ${statusClass(item.status)}">${escapeHtml(item.status)}</span>`;
  leaf.innerHTML=`<div><strong>${escapeHtml(item.botao||'Sem botao')}</strong><small>${escapeHtml(item.tela||'Sem tela')}</small></div><div class="leaf-statuses">${statuses}</div>`;
  return leaf;
}
function escapeHtml(value){const div=document.createElement('div');div.textContent=String(value??'');return div.innerHTML}
function createAccessTree(container,items){
  const root={children:{},items:[]};
  items.forEach(item=>addNode(root,splitPath(item.caminho),item));
  container.innerHTML='';
  Object.entries(root.children).sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([name,node],index)=>container.appendChild(renderBranch(name,node,index===0)));
  root.items.forEach(item=>container.appendChild(renderLeaf(item)));
  if(!items.length) container.innerHTML='<p class="empty-state">Nenhum acesso encontrado.</p>';
}
document.querySelectorAll('[data-access-tree]').forEach(container=>{
  const source=document.getElementById(container.dataset.accessTree);
  if(!source) return;
  try{createAccessTree(container,JSON.parse(source.textContent))}catch(error){container.innerHTML='<p class="empty-state">Falha ao montar a arvore de acessos.</p>';console.error(error)}
});
document.querySelectorAll('[data-tree-filter]').forEach(input=>input.addEventListener('input',()=>{
  const tree=document.getElementById(input.dataset.treeFilter); if(!tree)return;
  const q=input.value.toLocaleLowerCase('pt-BR').trim();
  tree.querySelectorAll('.access-leaf').forEach(leaf=>leaf.hidden=q&&!leaf.innerText.toLocaleLowerCase('pt-BR').includes(q));
  tree.querySelectorAll('details').forEach(node=>{const visible=[...node.querySelectorAll('.access-leaf')].some(x=>!x.hidden);node.hidden=!visible;if(q&&visible)node.open=true});
}));
'''
(STATIC / 'tree.js').write_text(TREE_JS, encoding='utf-8', newline='\n')

base_path=TEMPLATES/'base.html'
base=base_path.read_text(encoding='utf-8')
if "path='/tree.js'" not in base:
    base=base.replace('</body>', "<script src=\"{{ url_for('static', path='/tree.js') }}\"></script>\n</body>")
base_path.write_text(base,encoding='utf-8',newline='\n')

FUNCIONARIO='''{% extends "base.html" %}
{% block title %}{{ funcionario.nome }}{% endblock %}
{% block content %}
<a class="back" href="/estrutura">Voltar para estrutura atual</a>
<section class="hero compact"><p class="eyebrow">Funcionario</p><h1>{{ funcionario.nome }}</h1><p>{{ funcionario.login }} | {{ funcionario.departamento.nome if funcionario.departamento else 'Departamento nao definido' }}</p></section>
<section class="profile-layout">
  <article class="panel"><h2>Perfis vinculados</h2><div class="chips">{% for vinculo in funcionario.perfis %}<span>{{ vinculo.perfil.nome }}</span>{% else %}<p>Nenhum perfil vinculado.</p>{% endfor %}</div></article>
  <article class="panel"><h2>Consolidado</h2><div class="stats"><span><b>{{ acessos|selectattr('status','equalto','Permitido')|list|length }}</b> Permitidos</span><span><b>{{ acessos|selectattr('status','equalto','Negado')|list|length }}</b> Negados</span><span><b>{{ acessos|length }}</b> Total</span></div></article>
</section>
<section class="panel"><div class="panel-title"><h2>Arvore de acessos consolidada</h2><input type="search" placeholder="Pesquisar modulo, tela ou botao" data-tree-filter="employee-access-tree"></div>
<script type="application/json" id="employee-access-data">{{ acessos|tojson }}</script><div id="employee-access-tree" class="access-tree" data-access-tree="employee-access-data"></div></section>
{% endblock %}
'''
(TEMPLATES/'funcionario.html').write_text(FUNCIONARIO,encoding='utf-8',newline='\n')

PERFIL='''{% extends "base.html" %}
{% block title %}{{ perfil.nome }}{% endblock %}
{% block content %}
<a class="back" href="/perfis">Voltar para perfis atuais</a>
<section class="hero compact"><p class="eyebrow">Perfil atual</p><h1>{{ perfil.nome }}</h1><p>Situacao: {{ perfil.situacao }} | Atualizacao: {{ perfil.ultima_atualizacao or 'Nao informada' }}</p></section>
<section class="profile-layout"><article class="panel"><h2>Resumo</h2><div class="stats"><span><b>{{ usuarios|length }}</b> Usuarios</span><span><b>{{ permitidos }}</b> Permitidos</span><span><b>{{ negados }}</b> Negados</span><span><b>{{ acessos|length }}</b> Total</span></div></article>
<article class="panel"><div class="panel-title"><h2>Usuarios vinculados</h2><input type="search" placeholder="Pesquisar usuario" data-filter="profile-users"></div><div class="table-wrap small-table"><table id="profile-users"><thead><tr><th>Nome</th><th>Login</th><th>Departamento</th></tr></thead><tbody>{% for usuario in usuarios %}<tr><td>{{ usuario.nome }}</td><td>{{ usuario.login }}</td><td>{{ usuario.departamento.nome if usuario.departamento else 'Nao definido' }}</td></tr>{% else %}<tr><td colspan="3">Nenhum usuario vinculado.</td></tr>{% endfor %}</tbody></table></div></article></section>
<section class="panel"><div class="panel-title"><h2>Arvore de acessos do perfil</h2><input type="search" placeholder="Pesquisar modulo, tela ou botao" data-tree-filter="profile-access-tree"></div>
<script type="application/json" id="profile-access-data">[{% for acesso, status in acessos %}{"caminho":{{ acesso.caminho_completo|tojson }},"tela":{{ acesso.tela_final|tojson }},"botao":{{ acesso.botao|tojson }},"status":{{ status|tojson }}}{% if not loop.last %},{% endif %}{% endfor %}]</script><div id="profile-access-tree" class="access-tree" data-access-tree="profile-access-data"></div></section>
{% endblock %}
'''
(TEMPLATES/'perfil.html').write_text(PERFIL,encoding='utf-8',newline='\n')

COMPARAR='''{% extends "base.html" %}
{% block title %}Comparar perfis{% endblock %}
{% block content %}
<section class="hero"><p class="eyebrow">Analise</p><h1>Comparar perfis</h1><p>Compare dois perfis atuais em uma arvore hierarquica de acessos.</p></section>
<form class="compare-form" method="get"><label>Perfil A<select name="perfil_a" required><option value="">Selecione</option>{% for item in perfis %}<option value="{{ item.id }}" {% if perfil_a and item.id == perfil_a.id %}selected{% endif %}>{{ item.nome }}</option>{% endfor %}</select></label><label>Perfil B<select name="perfil_b" required><option value="">Selecione</option>{% for item in perfis %}<option value="{{ item.id }}" {% if perfil_b and item.id == perfil_b.id %}selected{% endif %}>{{ item.nome }}</option>{% endfor %}</select></label><label>Pesquisar<input name="busca" value="{{ busca }}" placeholder="Tela, botao ou caminho"></label><label>Exibir<select name="categoria"><option value="todos">Todos</option><option value="manter" {% if categoria == 'manter' %}selected{% endif %}>Manter</option><option value="adicionar" {% if categoria == 'adicionar' %}selected{% endif %}>Adicionar</option><option value="remover" {% if categoria == 'remover' %}selected{% endif %}>Remover</option></select></label><button type="submit">Comparar</button><a class="secondary" href="/comparar">Limpar</a></form>
{% if resultado %}<section class="compare-summary"><article class="keep"><span>Manter</span><strong>{{ resultado.manter|length }}</strong></article><article class="add"><span>Adicionar</span><strong>{{ resultado.adicionar|length }}</strong></article><article class="remove"><span>Remover</span><strong>{{ resultado.remover|length }}</strong></article></section>
{% for titulo,nome,classe in [('Manter','manter','keep'),('Adicionar','adicionar','add'),('Remover','remover','remove')] %}<section class="panel compare-section {{ classe }}"><div class="panel-title"><h2>{{ titulo }}</h2><span>{{ resultado[nome]|length }} itens</span></div><script type="application/json" id="compare-{{ nome }}-data">[{% for item in resultado[nome] %}{"caminho":{{ item.caminho|tojson }},"tela":{{ item.tela|tojson }},"botao":{{ item.botao|tojson }},"status":{{ item.status_a|tojson }},"statusA":{{ item.status_a|tojson }},"statusB":{{ item.status_b|tojson }}}{% if not loop.last %},{% endif %}{% endfor %}]</script><div class="access-tree" data-access-tree="compare-{{ nome }}-data"></div></section>{% endfor %}
{% else %}<section class="panel"><p>Selecione os dois perfis para iniciar a comparacao.</p></section>{% endif %}
{% endblock %}
'''
(TEMPLATES/'comparar.html').write_text(COMPARAR,encoding='utf-8',newline='\n')

css_path=STATIC/'styles.css'
css=css_path.read_text(encoding='utf-8')
EXTRA='''
.access-tree{display:flex;flex-direction:column;gap:8px;margin-top:12px}.access-node{border:1px solid #dbe4ec;border-radius:10px;background:#fbfcfe;overflow:hidden}.access-node>summary{display:flex;justify-content:space-between;align-items:center;padding:11px 13px;cursor:pointer;font-weight:700;color:#17365d}.access-node>summary small{padding:2px 7px;border-radius:999px;background:#e8eef5;color:#475467}.access-branch{display:flex;flex-direction:column;gap:7px;padding:0 10px 10px 18px}.access-leaf{display:grid;grid-template-columns:minmax(220px,1fr) auto;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;border-left:5px solid #98a2b3;background:white}.access-leaf>div:first-child{min-width:0}.access-leaf strong,.access-leaf small{display:block;overflow-wrap:anywhere}.access-leaf small{margin-top:3px;color:#667085}.access-leaf.is-allowed{border-left-color:#15803d;background:#ecfdf3}.access-leaf.is-denied{border-left-color:#dc2626;background:#fff1f0}.access-leaf.is-unknown{border-left-color:#98a2b3}.access-status,.compare-status{display:inline-block;padding:4px 9px;border-radius:999px;font-weight:700;white-space:nowrap}.access-status.is-allowed,.compare-status.is-allowed{background:#bbf7d0;color:#075b24}.access-status.is-denied,.compare-status.is-denied{background:#fecaca;color:#8a1712}.access-status.is-unknown,.compare-status.is-unknown{background:#e4e7ec;color:#475467}.leaf-statuses{display:flex;align-items:center;gap:7px}.compare-arrow{color:#667085}.empty-state{color:#667085}@media(max-width:700px){.access-leaf{grid-template-columns:1fr}.leaf-statuses{justify-content:flex-start}}
'''
if '.access-tree{' not in css:
    css += EXTRA
css_path.write_text(css,encoding='utf-8',newline='\n')

py_compile.compile(str(MAIN),doraise=True)
print('Arvore de acessos e cores de status configuradas com sucesso.')
print(r'Execute: uvicorn app.main:app --reload')
