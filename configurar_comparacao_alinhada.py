from pathlib import Path
import py_compile

ROOT = Path.cwd()
MAIN = ROOT / 'app' / 'main.py'
TEMPLATES = ROOT / 'app' / 'templates'
STATIC = ROOT / 'app' / 'static'

if not MAIN.exists():
    raise SystemExit('Execute na raiz C:\\Projetos\\gestao-acessos-web')

TEMPLATES.mkdir(parents=True, exist_ok=True)
STATIC.mkdir(parents=True, exist_ok=True)
text = MAIN.read_text(encoding='utf-8')

BACKEND = '''def _mapa_comparacao_perfil(session: Session, perfil_id: int):
    linhas = session.execute(
        select(Acesso, PerfilAcesso.status)
        .join(PerfilAcesso, PerfilAcesso.acesso_id == Acesso.id)
        .where(PerfilAcesso.perfil_id == perfil_id)
    ).all()
    return {
        acesso.id: {
            "id": acesso.id,
            "caminho": acesso.caminho_completo,
            "tela": acesso.tela_final,
            "botao": acesso.botao,
            "status": status or "Nao identificado",
        }
        for acesso, status in linhas
    }


def _comparar_perfis_alinhados(session: Session, perfil_a_id: int, perfil_b_id: int):
    mapa_a = _mapa_comparacao_perfil(session, perfil_a_id)
    mapa_b = _mapa_comparacao_perfil(session, perfil_b_id)
    resultado = []

    for acesso_id in set(mapa_a) | set(mapa_b):
        acesso_a = mapa_a.get(acesso_id)
        acesso_b = mapa_b.get(acesso_id)
        base = acesso_a or acesso_b
        status_a = acesso_a["status"] if acesso_a else "Ausente"
        status_b = acesso_b["status"] if acesso_b else "Ausente"
        normal_a = str(status_a).strip().casefold()
        normal_b = str(status_b).strip().casefold()

        if normal_a == normal_b:
            categoria = "igual"
        elif acesso_a is None:
            categoria = "somente_b"
        elif acesso_b is None:
            categoria = "somente_a"
        else:
            categoria = "status_diferente"

        resultado.append({
            "id": acesso_id,
            "caminho": base["caminho"],
            "tela": base["tela"],
            "botao": base["botao"],
            "status_a": status_a,
            "status_b": status_b,
            "categoria": categoria,
        })

    return sorted(
        resultado,
        key=lambda item: (
            item["caminho"].casefold(),
            item["tela"].casefold(),
            item["botao"].casefold(),
        ),
    )


@app.get("/comparar", response_class=HTMLResponse)
def comparar_perfis_alinhados(
    request: Request,
    session: DatabaseSession,
    perfil_a: int | None = None,
    perfil_b: int | None = None,
):
    perfis = session.scalars(select(Perfil).order_by(Perfil.nome)).all()
    selecionado_a = session.get(Perfil, perfil_a) if perfil_a else None
    selecionado_b = session.get(Perfil, perfil_b) if perfil_b else None
    itens = []

    if selecionado_a and selecionado_b:
        itens = _comparar_perfis_alinhados(
            session,
            selecionado_a.id,
            selecionado_b.id,
        )

    totais = {
        "total": len(itens),
        "iguais": sum(1 for item in itens if item["categoria"] == "igual"),
        "diferentes": sum(1 for item in itens if item["categoria"] == "status_diferente"),
        "somente_a": sum(1 for item in itens if item["categoria"] == "somente_a"),
        "somente_b": sum(1 for item in itens if item["categoria"] == "somente_b"),
    }

    return templates.TemplateResponse(
        request=request,
        name="comparar.html",
        context={
            "perfis": perfis,
            "perfil_a": selecionado_a,
            "perfil_b": selecionado_b,
            "itens": itens,
            "totais": totais,
        },
    )
'''


def find_route_block(source: str, route: str):
    lines = source.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith('@app.') and f'"{route}"' in line:
            start = i
            break
    if start is None:
        return source.rstrip() + '\n\n' + BACKEND + '\n'
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith('@app.'):
            end = i
            break
    return ''.join(lines[:start]) + BACKEND.rstrip() + '\n\n' + ''.join(lines[end:])

# Remove helpers de comparação anteriores para evitar colisões conhecidas.
for old_name in ('mapa_perfil', 'comparar_mapas'):
    lines = text.splitlines(keepends=True)
    idx = next((i for i,l in enumerate(lines) if l.startswith(f'def {old_name}(')), None)
    if idx is not None:
        end = len(lines)
        for j in range(idx + 1, len(lines)):
            if lines[j].startswith('def ') or lines[j].startswith('@app.'):
                end = j
                break
        text = ''.join(lines[:idx] + lines[end:])

text = find_route_block(text, '/comparar')
MAIN.write_text(text, encoding='utf-8', newline='\n')
py_compile.compile(str(MAIN), doraise=True)

TEMPLATE = '''{% extends "base.html" %}
{% block title %}Comparar perfis{% endblock %}
{% block content %}
<section class="hero compare-hero">
  <p class="eyebrow">Comparação de permissões</p>
  <h1>Comparar dois perfis</h1>
  <p>Uma árvore compartilhada mantém caminhos, telas e botões alinhados.</p>
</section>

<form class="compare-selectors" method="get">
  <label>Perfil A
    <select name="perfil_a" required>
      <option value="">Selecione o Perfil A</option>
      {% for perfil in perfis %}<option value="{{ perfil.id }}" {% if perfil_a and perfil.id == perfil_a.id %}selected{% endif %}>{{ perfil.nome }}</option>{% endfor %}
    </select>
  </label>
  <button class="swap-button" type="button" id="swap-profiles" title="Inverter perfis">⇄</button>
  <label>Perfil B
    <select name="perfil_b" required>
      <option value="">Selecione o Perfil B</option>
      {% for perfil in perfis %}<option value="{{ perfil.id }}" {% if perfil_b and perfil.id == perfil_b.id %}selected{% endif %}>{{ perfil.nome }}</option>{% endfor %}
    </select>
  </label>
  <button type="submit">Comparar</button>
</form>

{% if perfil_a and perfil_b %}
<section class="compare-cards">
  <article><span>Total analisado</span><strong>{{ totais.total }}</strong></article>
  <article class="equal"><span>Iguais</span><strong>{{ totais.iguais }}</strong></article>
  <article class="different"><span>Status diferente</span><strong>{{ totais.diferentes }}</strong></article>
  <article class="only-a"><span>Somente {{ perfil_a.nome }}</span><strong>{{ totais.somente_a }}</strong></article>
  <article class="only-b"><span>Somente {{ perfil_b.nome }}</span><strong>{{ totais.somente_b }}</strong></article>
</section>

<section class="compare-toolbar">
  <div class="compare-tabs">
    <button class="active" type="button" data-compare-view="tree">Árvore alinhada</button>
    <button type="button" data-compare-view="paths">Somente caminhos</button>
  </div>
  <label class="difference-toggle"><input type="checkbox" id="only-differences" checked> Somente diferenças</label>
  <select id="difference-filter">
    <option value="todos">Todas as diferenças</option>
    <option value="status_diferente">Status diferente</option>
    <option value="somente_a">Somente Perfil A</option>
    <option value="somente_b">Somente Perfil B</option>
    <option value="igual">Iguais</option>
  </select>
  <input id="compare-search" placeholder="Pesquisar caminho, tela ou botão">
  <button type="button" id="expand-all">Expandir tudo</button>
  <button type="button" id="collapse-all">Recolher tudo</button>
</section>

<script type="application/json" id="comparison-data">{{ itens|tojson }}</script>
<section id="aligned-comparison" class="aligned-comparison" data-view="tree">
  <header class="comparison-header">
    <div>Caminho / tela / botão</div>
    <div>{{ perfil_a.nome }}</div>
    <div>{{ perfil_b.nome }}</div>
  </header>
  <div id="comparison-tree" class="comparison-tree"></div>
  <div id="comparison-paths" class="comparison-paths"></div>
</section>
{% else %}
<section class="panel compare-empty"><p>Selecione dois perfis para iniciar a comparação.</p></section>
{% endif %}
{% endblock %}
'''
(TEMPLATES / 'comparar.html').write_text(TEMPLATE, encoding='utf-8', newline='\n')

JS = r'''(()=>{
 const source=document.getElementById('comparison-data');
 if(!source)return;
 const items=JSON.parse(source.textContent||'[]');
 const container=document.getElementById('aligned-comparison');
 const tree=document.getElementById('comparison-tree');
 const paths=document.getElementById('comparison-paths');
 const search=document.getElementById('compare-search');
 const onlyDiff=document.getElementById('only-differences');
 const filter=document.getElementById('difference-filter');
 const norm=v=>String(v||'').trim().toLocaleLowerCase('pt-BR');
 const esc=v=>{const d=document.createElement('div');d.textContent=String(v??'');return d.innerHTML};
 const stateClass=v=>norm(v)==='permitido'?'allowed':norm(v)==='negado'?'denied':'absent';
 const state=v=>`<span class="compare-state ${stateClass(v)}"><b>${stateClass(v)==='allowed'?'✓':stateClass(v)==='denied'?'✕':'•'}</b>${esc(v)}</span>`;
 const parts=v=>String(v||'Sem caminho').split(/\s*>\s*|\s*\/\s*|\s*\\\s*/).map(x=>x.trim()).filter(Boolean);
 const root={children:new Map(),screens:new Map()};
 for(const item of items){let node=root;for(const part of parts(item.caminho)){if(!node.children.has(part))node.children.set(part,{children:new Map(),screens:new Map()});node=node.children.get(part)}const screen=item.tela||'Sem tela';if(!node.screens.has(screen))node.screens.set(screen,[]);node.screens.get(screen).push(item)}
 function visible(item){const q=norm(search.value);if(onlyDiff.checked&&item.categoria==='igual')return false;if(filter.value!=='todos'&&item.categoria!==filter.value)return false;return !q||norm(`${item.caminho} ${item.tela} ${item.botao}`).includes(q)}
 function row(item,pathMode=false){const e=document.createElement('div');e.className=`comparison-row ${item.categoria}`;e.dataset.category=item.categoria;e.dataset.search=norm(`${item.caminho} ${item.tela} ${item.botao}`);e.innerHTML=`<div class="comparison-name">${pathMode?`<small>${esc(item.caminho)} › ${esc(item.tela)} ›</small>`:''}<span>${esc(item.botao)}</span><em>${item.categoria==='igual'?'Igual':item.categoria==='status_diferente'?'Status diferente':item.categoria==='somente_a'?'Somente Perfil A':'Somente Perfil B'}</em></div><div>${state(item.status_a)}</div><div>${state(item.status_b)}</div>`;e.hidden=!visible(item);return e}
 function countVisible(node){let n=0;for(const list of node.screens.values())n+=list.filter(visible).length;for(const child of node.children.values())n+=countVisible(child);return n}
 function branch(name,node,depth=0){const details=document.createElement('details');details.className='comparison-branch';details.open=depth===0;const count=countVisible(node);details.hidden=count===0;details.innerHTML=`<summary><span class="branch-toggle"></span><span class="branch-folder"></span><strong>${esc(name)}</strong><small>${count}</small></summary>`;const body=document.createElement('div');body.className='comparison-children';[...node.children.entries()].sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([n,v])=>body.appendChild(branch(n,v,depth+1)));[...node.screens.entries()].sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([screen,list])=>{const block=document.createElement('section');block.className='comparison-screen';const shown=list.filter(visible).length;block.hidden=shown===0;block.innerHTML=`<div class="screen-heading"><span>✓</span><strong>${esc(screen)}</strong><small>${shown}</small></div>`;list.sort((a,b)=>String(a.botao).localeCompare(String(b.botao),'pt-BR')).forEach(item=>block.appendChild(row(item)));body.appendChild(block)});details.appendChild(body);return details}
 function render(){tree.innerHTML='';[...root.children.entries()].sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([name,node])=>tree.appendChild(branch(name,node)));paths.innerHTML='';items.slice().sort((a,b)=>`${a.caminho}${a.tela}${a.botao}`.localeCompare(`${b.caminho}${b.tela}${b.botao}`,'pt-BR')).forEach(item=>{const r=row(item,true);paths.appendChild(r)})}
 document.querySelectorAll('[data-compare-view]').forEach(button=>button.onclick=()=>{container.dataset.view=button.dataset.compareView;document.querySelectorAll('[data-compare-view]').forEach(x=>x.classList.toggle('active',x===button))});
 [search,onlyDiff,filter].forEach(control=>control.addEventListener('input',render));
 document.getElementById('expand-all').onclick=()=>tree.querySelectorAll('details').forEach(x=>x.open=true);
 document.getElementById('collapse-all').onclick=()=>tree.querySelectorAll('details').forEach(x=>x.open=false);
 const swap=document.getElementById('swap-profiles');if(swap)swap.onclick=()=>{const a=document.querySelector('[name="perfil_a"]'),b=document.querySelector('[name="perfil_b"]'),value=a.value;a.value=b.value;b.value=value};
 render();
})();
'''
(STATIC / 'comparison.js').write_text(JS, encoding='utf-8', newline='\n')

CSS = r'''
.compare-selectors{display:grid;grid-template-columns:1fr auto 1fr auto;gap:10px;align-items:end;margin-bottom:16px}.compare-selectors label{display:flex;flex-direction:column;gap:6px;color:#475467;font-size:13px}.compare-selectors select,.compare-selectors button,.compare-toolbar select,.compare-toolbar input,.compare-toolbar button{padding:9px 11px;border:1px solid #b8c3cd;border-radius:7px;background:#fff}.compare-selectors button[type="submit"]{background:#1f4e78;color:#fff;border-color:#1f4e78}.swap-button{font-size:20px}.compare-cards{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:10px;margin-bottom:14px}.compare-cards article{padding:13px;background:#fff;border:1px solid #d7e0e8;border-left:4px solid #98a2b3;border-radius:8px}.compare-cards span{display:block;color:#667085;font-size:12px}.compare-cards strong{font-size:27px}.compare-cards .equal{border-left-color:#15803d}.compare-cards .different{border-left-color:#d97706}.compare-cards .only-a{border-left-color:#2563eb}.compare-cards .only-b{border-left-color:#7c3aed}.compare-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}.compare-tabs{display:flex;gap:4px}.compare-tabs button.active{background:#17365d;color:#fff}.difference-toggle{display:flex;align-items:center;gap:5px}.aligned-comparison{background:#fff;border:1px solid #cfd8e1;border-radius:8px;overflow:hidden}.comparison-header,.comparison-row{display:grid;grid-template-columns:minmax(420px,1.6fr) minmax(170px,.7fr) minmax(170px,.7fr)}.comparison-header{position:sticky;top:0;z-index:2;background:#edf4fa;font-weight:700;color:#17365d}.comparison-header>div,.comparison-row>div{padding:8px 10px;border-right:1px solid #d9e0e6}.comparison-header>div:last-child,.comparison-row>div:last-child{border-right:0}.comparison-tree,.comparison-paths{max-height:680px;overflow:auto;padding:8px}.comparison-paths{display:none}.aligned-comparison[data-view="paths"] .comparison-tree{display:none}.aligned-comparison[data-view="paths"] .comparison-paths{display:block}.comparison-branch summary{list-style:none;display:flex;align-items:center;gap:5px;min-height:25px;cursor:pointer}.comparison-branch summary::-webkit-details-marker{display:none}.branch-toggle:before{content:'+';display:grid;place-items:center;width:12px;height:12px;border:1px solid #667085;font-size:10px}.comparison-branch[open]>summary .branch-toggle:before{content:'−'}.branch-folder:before{content:'📁'}.comparison-branch[open]>summary .branch-folder:before{content:'📂'}.comparison-branch summary small,.screen-heading small{margin-left:auto;color:#667085}.comparison-children{margin-left:6px;padding-left:15px;border-left:1px dotted #98a2b3}.screen-heading{display:flex;align-items:center;gap:5px;padding:4px 5px;color:#17365d}.screen-heading>span{color:#159447}.comparison-row{border-bottom:1px solid #edf0f2;border-left:4px solid transparent}.comparison-row.status_diferente{border-left-color:#d97706;background:#fffaf0}.comparison-row.somente_a{border-left-color:#2563eb;background:#f3f7ff}.comparison-row.somente_b{border-left-color:#7c3aed;background:#faf5ff}.comparison-row.igual{border-left-color:#15803d}.comparison-name small,.comparison-name span{display:block}.comparison-name small{color:#667085}.comparison-name em{display:inline-block;margin-top:3px;color:#667085;font-size:11px;font-style:normal}.compare-state{display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700}.compare-state.allowed{background:#d9fbe3;color:#075b24}.compare-state.denied{background:#ffe0dd;color:#8a1712}.compare-state.absent{background:#e9edf0;color:#475467}.compare-empty{padding:18px}@media(max-width:1050px){.compare-cards{grid-template-columns:repeat(2,1fr)}.comparison-header,.comparison-row{grid-template-columns:minmax(260px,1.2fr) minmax(130px,.7fr) minmax(130px,.7fr)}}@media(max-width:720px){.compare-selectors{grid-template-columns:1fr}.swap-button{display:none}.compare-cards{grid-template-columns:1fr}.comparison-header,.comparison-row{grid-template-columns:1fr}.comparison-header{display:none}.comparison-row>div{border-right:0}.comparison-row>div:nth-child(2):before{content:'Perfil A: ';font-weight:700}.comparison-row>div:nth-child(3):before{content:'Perfil B: ';font-weight:700}}
'''
styles = STATIC / 'styles.css'
current = styles.read_text(encoding='utf-8') if styles.exists() else ''
marker = '/* COMPARACAO_ALINHADA_V1 */'
if marker not in current:
    current += '\n' + marker + '\n' + CSS
styles.write_text(current, encoding='utf-8', newline='\n')

base = TEMPLATES / 'base.html'
base_text = base.read_text(encoding='utf-8')
script = "<script src=\"{{ url_for('static',path='/comparison.js') }}\"></script>"
if script not in base_text:
    base_text = base_text.replace('</body>', script + '</body>')
base.write_text(base_text, encoding='utf-8', newline='\n')

print('Tela de comparacao alinhada instalada com sucesso.')
print('app/main.py compilado com sucesso.')
print('Reinicie o servidor e use Ctrl+F5 no navegador.')
