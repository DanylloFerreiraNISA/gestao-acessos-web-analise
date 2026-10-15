(()=>{
  if(location.pathname==='/login') return;
  const IDLE_MS=10*60*1000;
  let last=Date.now(),lastPing=0,timer=null;
  const loginUrl=()=>`/login?next=${encodeURIComponent(location.pathname+location.search)}&reason=inactive`;
  const expire=()=>location.replace(loginUrl());
  function schedule(){clearTimeout(timer);timer=setTimeout(expire,Math.max(0,IDLE_MS-(Date.now()-last)))}
  async function markActivity(){
    last=Date.now();
    schedule();
    if(Date.now()-lastPing<60000) return;
    lastPing=Date.now();
    try{
      const response=await fetch('/session/activity',{method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'}});
      if(response.status===401) expire();
    }catch(_error){}
  }
  ['click','keydown','mousemove','scroll','touchstart'].forEach(eventName=>addEventListener(eventName,markActivity,{passive:true}));
  schedule();
})();
