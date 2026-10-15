from pathlib import Path
import py_compile

ROOT = Path.cwd()
BASE = ROOT / 'app' / 'templates' / 'base.html'
LOGIN = ROOT / 'app' / 'templates' / 'login.html'
ACCESS = ROOT / 'app' / 'access_control.py'
JS = ROOT / 'app' / 'static' / 'session-activity.js'

for path in (BASE, LOGIN, ACCESS):
    if not path.exists():
        raise SystemExit(f'Arquivo nao encontrado: {path}')

# 1. O monitor de inatividade só pode existir em páginas autenticadas.
base = BASE.read_text(encoding='utf-8')
old_variants = [
    '<script src="{{ url_for(\'static\', path=\'/session-activity.js\') }}"></script>',
    '<script src="{{ url_for("static", path="/session-activity.js") }}"></script>',
]
for old in old_variants:
    base = base.replace(old, '')

conditional_script = '''{% if current_user %}<script src="{{ url_for('static', path='/session-activity.js') }}"></script>{% endif %}'''
if conditional_script not in base:
    base = base.replace('{% block scripts %}', conditional_script + '\n{% block scripts %}')
BASE.write_text(base, encoding='utf-8', newline='\n')

# 2. Torna o JavaScript defensivo: não executa na tela de login.
activity_js = r'''(()=>{
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
'''
JS.write_text(activity_js, encoding='utf-8', newline='\n')

# 3. Garante que o formulário use exatamente os nomes esperados pelo backend.
login = LOGIN.read_text(encoding='utf-8')
login = login.replace('name="email"', 'name="login"')
if 'name="next_url"' not in login:
    login = login.replace('<form class="auth-card" method="post">', '<form class="auth-card" method="post"><input type="hidden" name="next_url" value="{{ next_url or \'/portal\' }}">', 1)
LOGIN.write_text(login, encoding='utf-8', newline='\n')

# 4. Corrige o middleware para não classificar abertura inicial como expiração.
access = ACCESS.read_text(encoding='utf-8')
old_redirect = "return RedirectResponse(f'/login?next={request.url.path}&reason=inactive', status_code=303)"
new_redirect = "return RedirectResponse(f'/login?next={request.url.path}', status_code=303)"
access = access.replace(old_redirect, new_redirect)
ACCESS.write_text(access, encoding='utf-8', newline='\n')

py_compile.compile(str(ACCESS), doraise=True)
print('Loop da tela de login corrigido.')
print('- Monitor de inatividade removido da pagina de login')
print('- Formulario alinhado com o backend')
print('- Redirecionamento inicial sem mensagem falsa de expiracao')
