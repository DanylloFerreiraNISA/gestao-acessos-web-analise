(() => {
  const one=(s,r=document)=>r.querySelector(s), all=(s,r=document)=>[...r.querySelectorAll(s)];
  all('[data-delete]').forEach(b=>b.addEventListener('click',()=>{const d=one('#deleteDialog');if(!d)return;one('#deleteForm').action=`/portal/propostas/${b.dataset.delete}/excluir`;one('#deleteText').textContent=`Deseja excluir “${b.dataset.name}”?`;d.showModal()}));
  all('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
  const origin=one('#origin'), profile=one('#sourceProfile'), employee=one('#sourceEmployee'), note=one('#baseNote');
  function sourceFields(){if(!origin)return;const p=origin.value==='COPIADO_DE_PERFIL';profile?.closest('[data-source]')?.classList.toggle('hidden-source',!p);employee?.closest('[data-source]')?.classList.toggle('hidden-source',p);if(profile){profile.required=p;if(!p)profile.value=''}if(employee){employee.required=!p;if(p)employee.value=''}if(note)note.textContent=p?'Selecione o perfil. Somente os acessos permitidos começarão marcados.':'Selecione o funcionário. Somente os acessos consolidados permitidos começarão marcados.'}
  origin?.addEventListener('change',sourceFields);sourceFields();
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  function start(root){
    if(root.dataset.ready)return;root.dataset.ready='1';
    const catalog=JSON.parse(one('[data-editor-catalog]',root)?.textContent||'[]');
    const initial=new Set(JSON.parse(one('[data-editor-selected]',root)?.textContent||'[]').map(String));
    const screens=new Map();
    catalog.forEach(a=>{const key=`${a.path}||${a.screen}`;if(!screens.has(key))screens.set(key,{key,path:a.path,screen:a.screen,buttons:[]});screens.get(key).buttons.push({id:String(a.id),name:a.button})});
    const tree=one('[data-editor-tree]',root), actions=one('[data-editor-actions]',root), inputs=one('[data-editor-inputs]',root);let active=[...screens.keys()].find(k=>screens.get(k).buttons.some(b=>initial.has(b.id)))||[...screens.keys()][0]||null;let search='',only=false;const selected=initial,expanded=new Set([...screens.values()].map(s=>s.path.split(' > ')[0]));
    function groups(){const r={};screens.forEach(s=>{let n=r;s.path.split(' > ').filter(Boolean).forEach(p=>n=n[p]??={_:{}});(n._screens??=[]).push(s)});return r}
    const count=s=>s.buttons.filter(b=>selected.has(b.id)).length, allowed=s=>count(s)>0, key=p=>p.join(' > ');
    function row(s){const n=count(s),txt=(s.path+' '+s.screen+' '+s.buttons.map(b=>b.name).join(' ')).toLowerCase(),show=(!search||txt.includes(search))&&(!only||n);return `<div class="pe-screen ${show?'':'pe-hidden'}"><button type="button" class="pe-screen-row ${s.key===active?'active':''}" data-screen="${esc(s.key)}"><span class="pe-state ${n?'allowed':'denied'}">${n?'✓':'×'}</span><span>${esc(s.screen)}</span><small>${n}</small></button></div>`}
    function drawTree(){function render(n,parts=[]){return Object.entries(n).filter(([x])=>!x.startsWith('_')).map(([name,ch])=>{const k=key([...parts,name]),open=expanded.has(k),inside=render(ch,[...parts,name])+(ch._screens||[]).map(row).join('');return `<div class="pe-branch"><button type="button" class="pe-folder" data-folder="${esc(k)}"><span>${open?'−':'+'}</span><i></i><b>${esc(name)}</b></button><div class="pe-children" ${open?'':'hidden'}>${inside}</div></div>`}).join('')}tree.innerHTML=render(groups())}
    function drawActions(){const s=screens.get(active);const empty=one('[data-editor-empty]',root),detail=one('[data-editor-detail]',root);if(!s){empty.hidden=false;detail.hidden=true;return}empty.hidden=true;detail.hidden=false;one('[data-editor-path]',root).textContent=s.path;one('[data-editor-title]',root).textContent=s.screen;const t=one('[data-editor-screen-toggle]',root);t.checked=allowed(s);t.indeterminate=count(s)>0&&count(s)<s.buttons.length;actions.innerHTML=s.buttons.map(b=>`<label class="pe-action"><input type="checkbox" data-access="${b.id}" ${selected.has(b.id)?'checked':''}><span>${esc(b.name)}</span><em class="${selected.has(b.id)?'allowed':'denied'}">${selected.has(b.id)?'Permitido':'Negado'}</em></label>`).join('')}
    function sync(){inputs.innerHTML=[...selected].map(id=>`<input type="hidden" name="access_ids" value="${id}">`).join('');one('[data-editor-screen-total]',root).textContent=[...screens.values()].filter(allowed).length;one('[data-editor-access-total]',root).textContent=selected.size}
    function refresh(){drawTree();drawActions();sync()}
    function setScreen(on){screens.get(active)?.buttons.forEach(b=>on?selected.add(b.id):selected.delete(b.id));refresh()}
    tree.addEventListener('click',e=>{const f=e.target.closest('[data-folder]');if(f){const k=f.dataset.folder;expanded.has(k)?expanded.delete(k):expanded.add(k);drawTree();return}const s=e.target.closest('[data-screen]');if(s){active=s.dataset.screen;refresh()}});
    actions.addEventListener('change',e=>{const i=e.target.closest('[data-access]');if(!i)return;i.checked?selected.add(i.dataset.access):selected.delete(i.dataset.access);refresh()});
    one('[data-editor-screen-toggle]',root).addEventListener('change',e=>setScreen(e.target.checked));one('[data-editor-allow-all]',root).addEventListener('click',()=>setScreen(true));one('[data-editor-deny-all]',root).addEventListener('click',()=>setScreen(false));one('[data-editor-search]',root).addEventListener('input',e=>{search=e.target.value.toLowerCase();drawTree()});one('[data-editor-only-selected]',root).addEventListener('change',e=>{only=e.target.checked;drawTree()});one('[data-editor-expand]',root).addEventListener('click',()=>{screens.forEach(s=>{let p=[];s.path.split(' > ').filter(Boolean).forEach(x=>{p.push(x);expanded.add(key(p))})});drawTree()});one('[data-editor-collapse]',root).addEventListener('click',()=>{expanded.clear();drawTree()});
    root.applyBaseIds=ids=>{selected.clear();ids.forEach(id=>selected.add(String(id)));active=[...screens.keys()].find(k=>allowed(screens.get(k)))||active;refresh()};refresh();
  }
  document.addEventListener('DOMContentLoaded',()=>all('[data-proposal-editor]').forEach(start));
  async function loadBase(){const root=one('[data-proposal-editor]');if(!origin||!root)return;const src=origin.value==='COPIADO_DE_PERFIL'?profile:employee;if(!src?.value)return;if(note)note.textContent='Carregando acessos da base...';try{const r=await fetch(`/portal/propostas/base-acessos?origin=${encodeURIComponent(origin.value)}&source_id=${encodeURIComponent(src.value)}`);if(!r.ok)throw new Error(await r.text());const d=await r.json();root.applyBaseIds?.(d.access_ids.map(String));if(note)note.textContent=`${d.access_ids.length} acesso(s) carregado(s).`;}catch(e){if(note)note.textContent='Não foi possível carregar os acessos da base.';console.error(e)}}
  profile?.addEventListener('change',loadBase);employee?.addEventListener('change',loadBase);
})();

// PROPOSTA_DO_ZERO_V3
(() => {
  const origin = document.querySelector('#origin');
  const profile = document.querySelector('#sourceProfile');
  const employee = document.querySelector('#sourceEmployee');
  const note = document.querySelector('#baseNote');
  if (!origin) return;

  const profileWrap = profile?.closest('[data-source]');
  const employeeWrap = employee?.closest('[data-source]');

  function applyZeroMode() {
    const zeroMode = origin.value === 'CRIADO_DO_ZERO';
    if (!zeroMode) return;

    profileWrap?.classList.add('hidden-source');
    employeeWrap?.classList.add('hidden-source');
    if (profile) { profile.required = false; profile.value = ''; }
    if (employee) { employee.required = false; employee.value = ''; }
    document.querySelectorAll('input[name="access_ids"]').forEach(input => {
      if (!input.dataset.zeroModeInitialized) input.checked = false;
      input.dataset.zeroModeInitialized = '1';
    });
    if (note) note.textContent = 'Criando do zero: selecione manualmente as telas e os botões desejados.';
  }

  origin.addEventListener('change', () => {
    document.querySelectorAll('input[name="access_ids"]').forEach(input => delete input.dataset.zeroModeInitialized);
    queueMicrotask(applyZeroMode);
  });

  applyZeroMode();
})();
