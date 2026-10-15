// ARVORES_RECOLHIVEIS_V3
const ClassicAccessTree=(()=>{
  const esc=value=>{const e=document.createElement('div');e.textContent=String(value??'');return e.innerHTML};
  const norm=value=>String(value||'').trim().toLocaleLowerCase('pt-BR');
  const statusClass=value=>norm(value)==='permitido'?'allowed':norm(value)==='negado'?'denied':'unknown';
  const pathParts=value=>String(value||'Sem caminho').split(/\s*>\s*|\s*\/\s*|\s*\\\s*/).map(x=>x.trim()).filter(Boolean);

  function makeNode(){return{children:new Map(),screens:new Map()}}
  function buildTree(items){
    const root=makeNode();
    for(const item of items){
      let node=root;
      for(const name of pathParts(item.caminho)){
        if(!node.children.has(name))node.children.set(name,makeNode());
        node=node.children.get(name);
      }
      const screen=item.tela||'Sem tela';
      if(!node.screens.has(screen))node.screens.set(screen,[]);
      node.screens.get(screen).push(item);
    }
    return root;
  }
  function icon(status){
    const type=statusClass(status);
    const symbol=type==='allowed'?'✓':type==='denied'?'✕':'•';
    return `<span class="classic-access-icon ${type}">${symbol}</span>`;
  }
  function badge(status){return `<span class="classic-badge ${statusClass(status)}">${esc(status||'Nao identificado')}</span>`}
  function accessLine(item,compare){
    const line=document.createElement('div');
    line.className=`classic-access-line ${statusClass(item.status)}`;
    line.dataset.search=norm(`${item.caminho} ${item.tela} ${item.botao} ${item.statusA||''} ${item.statusB||''}`);
    const state=compare?`${badge(item.statusA)}<span class="status-arrow">→</span>${badge(item.statusB)}`:badge(item.status);
    line.innerHTML=`${icon(item.status)}<span class="classic-access-name">${esc(item.botao||'Sem botao')}</span><span class="classic-access-status">${state}</span>`;
    return line;
  }
  function screenLine(name,items,onSelect){
    const button=document.createElement('button');
    button.type='button';
    button.className='classic-screen-line';
    button.dataset.search=norm(`${name} ${items.map(x=>x.botao).join(' ')}`);
    button.innerHTML=`<span class="screen-check">✓</span><span>${esc(name)}</span><small>${items.length}</small>`;
    button.addEventListener('click',()=>onSelect(name,items,button));
    return button;
  }
  function branch(name,node,onSelect,depth=0){
    const details=document.createElement('details');
    details.className='classic-branch';
    details.open=false;
    const summary=document.createElement('summary');
    summary.innerHTML=`<span class="classic-expander"></span><span class="classic-folder"></span><span class="classic-label">${esc(name)}</span>`;
    details.appendChild(summary);
    const children=document.createElement('div');
    children.className='classic-children';
    [...node.children.entries()].sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([child,value])=>children.appendChild(branch(child,value,onSelect,depth+1)));
    [...node.screens.entries()].sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([screen,items])=>children.appendChild(screenLine(screen,items,onSelect)));
    details.appendChild(children);
    return details;
  }
  function pathLine(item,compare){
    const row=document.createElement('div');
    row.className='classic-path-row';
    row.dataset.search=norm(`${item.caminho} ${item.tela} ${item.botao}`);
    const state=compare?`${badge(item.statusA)}<span class="status-arrow">→</span>${badge(item.statusB)}`:badge(item.status);
    row.innerHTML=`<div>${icon(item.status)}<span>${esc(item.caminho)} <b>›</b> ${esc(item.tela)} <b>›</b> ${esc(item.botao)}</span></div><div>${state}</div>`;
    return row;
  }
  function mountBrowser(root){
    if(root.dataset.mounted==='true')return;
    const source=document.getElementById(root.dataset.source);
    if(!source)return;
    let items=[];
    try{items=JSON.parse(source.textContent||'[]')}catch(error){console.error('JSON invalido da arvore',error);return}
    const compare=root.dataset.compare==='true';
    const toolbar=root.previousElementSibling?.classList.contains('classic-toolbar')?root.previousElementSibling:null;
      if(toolbar&&!toolbar.querySelector('[data-tree-expand-all]')){
        const controls=document.createElement('span');
        controls.className='tree-expand-controls';
        controls.innerHTML='<button type="button" class="secondary" data-tree-expand-all>Expandir tudo</button><button type="button" class="secondary" data-tree-collapse-all>Recolher tudo</button>';
        toolbar.appendChild(controls);
        controls.querySelector('[data-tree-expand-all]').addEventListener('click',()=>root.querySelectorAll('details').forEach(item=>item.open=true));
        controls.querySelector('[data-tree-collapse-all]').addEventListener('click',()=>root.querySelectorAll('details').forEach(item=>item.open=false));
      }
    const tree=root.querySelector('[data-classic-tree]');
    const accesses=root.querySelector('[data-classic-accesses]');
    const title=root.querySelector('[data-classic-title]');
    const paths=root.querySelector('[data-classic-paths]');
    const select=(screen,list,button)=>{
      root.querySelectorAll('.classic-screen-line.active').forEach(x=>x.classList.remove('active'));
      button.classList.add('active');
      title.textContent=screen;
      accesses.innerHTML='';
      list.slice().sort((a,b)=>String(a.botao).localeCompare(String(b.botao),'pt-BR')).forEach(item=>accesses.appendChild(accessLine(item,compare)));
    };
    const hierarchy=buildTree(items);
    tree.innerHTML='';
    [...hierarchy.children.entries()].sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([name,node])=>tree.appendChild(branch(name,node,select)));
    [...hierarchy.screens.entries()].sort(([a],[b])=>a.localeCompare(b,'pt-BR')).forEach(([screen,list])=>tree.appendChild(screenLine(screen,list,select)));
    accesses.innerHTML='<p class="classic-empty">Selecione uma tela na arvore.</p>';
    paths.innerHTML='';
    items.slice().sort((a,b)=>`${a.caminho}${a.tela}${a.botao}`.localeCompare(`${b.caminho}${b.tela}${b.botao}`,'pt-BR')).forEach(item=>paths.appendChild(pathLine(item,compare)));

    if(toolbar){
      toolbar.querySelectorAll('[data-classic-mode]').forEach(button=>button.addEventListener('click',()=>{
        root.dataset.mode=button.dataset.classicMode;
        toolbar.querySelectorAll('[data-classic-mode]').forEach(x=>x.classList.toggle('active',x===button));
      }));
      const search=toolbar.querySelector('[data-classic-search]');
      if(search)search.addEventListener('input',()=>{
        const query=norm(search.value);
        root.querySelectorAll('[data-search]').forEach(element=>element.hidden=Boolean(query)&&!element.dataset.search.includes(query));
        root.querySelectorAll('details').forEach(details=>{
          const visible=[...details.querySelectorAll('.classic-screen-line')].some(x=>!x.hidden);
          details.hidden=!visible;
          if(query&&visible)details.open=true;
        });
      });
    }
    root.dataset.mounted='true';
  }
  function activateProfileTab(button){
    const group=button.closest('[data-profile-tabs]');
    if(!group)return;
    const groupName=group.dataset.profileTabs;
    group.querySelectorAll('[data-profile-tab]').forEach(x=>x.classList.toggle('active',x===button));
    document.querySelectorAll(`[data-profile-panel="${groupName}"]`).forEach(panel=>panel.classList.toggle('active',panel.id===button.dataset.profileTab));
    const active=document.getElementById(button.dataset.profileTab);
    active?.querySelectorAll('[data-classic-browser]').forEach(mountBrowser);
  }
  function start(){
    document.querySelectorAll('[data-classic-browser]').forEach(mountBrowser);
    document.querySelectorAll('[data-profile-tab]').forEach(button=>button.addEventListener('click',()=>activateProfileTab(button)));
  }
  return{start};
})();
document.addEventListener('DOMContentLoaded',ClassicAccessTree.start);
