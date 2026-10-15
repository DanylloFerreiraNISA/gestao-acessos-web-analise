document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('[data-transfer-form]').forEach(form=>{
    const available=form.querySelector('[data-transfer-list="available"]');
    const selected=form.querySelector('[data-transfer-list="selected"]');
    if(!available||!selected)return;
    const move=(from,to,all=false)=>{
      [...from.options].filter(option=>all||option.selected).forEach(option=>{option.selected=false;to.add(option)});
      sort(to);sort(from);
    };
    const sort=select=>[...select.options].sort((a,b)=>a.text.localeCompare(b.text,'pt-BR')).forEach(o=>select.add(o));
    form.querySelector('[data-transfer="right"]')?.addEventListener('click',()=>move(available,selected));
    form.querySelector('[data-transfer="left"]')?.addEventListener('click',()=>move(selected,available));
    form.querySelector('[data-transfer="all-right"]')?.addEventListener('click',()=>move(available,selected,true));
    form.querySelector('[data-transfer="all-left"]')?.addEventListener('click',()=>move(selected,available,true));
    form.querySelectorAll('[data-transfer-search]').forEach(input=>input.addEventListener('input',()=>{
      const list=form.querySelector(`[data-transfer-list="${input.dataset.transferSearch}"]`);
      const q=input.value.trim().toLocaleLowerCase('pt-BR');
      [...list.options].forEach(option=>option.hidden=!!q&&!option.text.toLocaleLowerCase('pt-BR').includes(q));
    }));
    form.addEventListener('submit',()=>[...selected.options].forEach(option=>option.selected=true));
  });
});