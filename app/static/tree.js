function statusClass(value){
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
