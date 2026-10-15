(()=>{
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
