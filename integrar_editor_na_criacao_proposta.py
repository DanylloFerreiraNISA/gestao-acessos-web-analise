from pathlib import Path
from datetime import datetime
import py_compile, shutil, re

ROOT=Path.cwd().resolve(); AC=ROOT/'app'/'access_control.py'; T=ROOT/'app'/'templates'; S=ROOT/'app'/'static'
TPL=T/'proposal_new.html'; JS=S/'proposals.js'; CSS=S/'proposals.css'; files=[AC,TPL,JS,CSS]
missing=[str(p) for p in files if not p.exists()]
if missing: raise SystemExit('ERRO: arquivos ausentes; nada alterado: '+', '.join(missing))
backup=ROOT/f"backup_editor_criacao_proposta_{datetime.now():%Y%m%d_%H%M%S}"
for p in files:
 d=backup/p.relative_to(ROOT); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,d)

def route_block(code, decorator):
 start=code.find(decorator)
 if start<0: raise RuntimeError('Rota não encontrada: '+decorator)
 end=code.find('\n@router.',start+len(decorator))
 if end<0:end=len(code)
 return start,end,code[start:end]

try:
 code=AC.read_text(encoding='utf-8')
 # GET nova: inclui todos os acessos para o editor já abrir na criação.
 ds="@router.get('/portal/propostas/nova', response_class=HTMLResponse)"
 a,b,block=route_block(code,ds)
 old="'departments': departments"
 if old not in block: raise RuntimeError('Contexto departments não encontrado na rota nova')
 if "'accesses': accesses" not in block:
  anchor="    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if user.role in {ROLE_ADMIN, ROLE_ANALYST} else [user.department]\n"
  if anchor not in block: raise RuntimeError('Ponto de inclusão dos acessos não encontrado')
  block=block.replace(anchor,anchor+"    accesses = session.scalars(select(Acesso).order_by(Acesso.caminho_completo, Acesso.tela_final, Acesso.botao)).all()\n",1)
  block=block.replace(old,old+", 'accesses': accesses",1)
 code=code[:a]+block+code[b:]

 # Endpoint é inserido ANTES de /portal/propostas/{proposal_id}, evitando conflito com a rota dinâmica.
 detail="@router.get('/portal/propostas/{proposal_id}', response_class=HTMLResponse)"
 api='''@router.get('/portal/propostas/base-acessos')
def proposal_base_accesses(
    origin: str,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
    source_id: int,
):
    if origin == 'COPIADO_DE_PERFIL':
        if user.role == ROLE_MANAGER:
            allowed = session.scalar(select(func.count()).select_from(FuncionarioPerfil).join(Funcionario).where(FuncionarioPerfil.perfil_id == source_id, Funcionario.departamento_id == user.department_id))
            if not allowed: raise HTTPException(403, 'Perfil fora do departamento')
        access_map = proposal_access_map_from_profile(session, source_id)
    elif origin == 'CONSOLIDADO_FUNCIONARIO':
        employee = session.get(Funcionario, source_id)
        if not employee: raise HTTPException(404, 'Funcionario nao encontrado')
        enforce_department(user, employee.departamento_id)
        access_map = proposal_access_map_from_employee(session, source_id)
    else:
        raise HTTPException(400, 'Origem invalida')
    return {'access_ids': [int(access_id) for access_id, status in access_map.items() if str(status).casefold() == 'permitido']}


'''
 if "@router.get('/portal/propostas/base-acessos')" not in code:
  pos=code.find(detail)
  if pos<0: raise RuntimeError('Rota de detalhe não encontrada')
  code=code[:pos]+api+code[pos:]

 # POST: recebe seleção explícita da árvore e salva exatamente o que ficou marcado.
 ps="@router.post('/portal/propostas/nova')"
 a,b,block=route_block(code,ps)
 if 'access_selection_present:' not in block:
  sig_end=block.find('):')
  if sig_end<0: raise RuntimeError('Assinatura de proposal_create não encontrada')
  block=block[:sig_end]+", access_selection_present: Annotated[str, Form()] = '', access_ids: Annotated[list[int] | None, Form()] = None"+block[sig_end:]
 if "if access_selection_present == '1':" not in block:
  anchor="    elif origin in {'CONSOLIDADO_DEPARTAMENTO_COMUM', 'CONSOLIDADO_DEPARTAMENTO_UNIAO'}: access_map = proposal_access_map_from_department(session, department_id, origin)\n"
  if anchor in block:
   block=block.replace(anchor,anchor+"    if access_selection_present == '1': access_map = {access_id: 'Permitido' for access_id in set(access_ids or [])}\n",1)
  else:
   loop="    for access_id, access_status in access_map.items():"
   if loop not in block: raise RuntimeError('Ponto de gravação dos acessos não encontrado')
   block=block.replace(loop,"    if access_selection_present == '1': access_map = {access_id: 'Permitido' for access_id in set(access_ids or [])}\n"+loop,1)
 code=code[:a]+block+code[b:]
 AC.write_text(code,encoding='utf-8',newline='\n')

 TPL.write_text('''{% extends "base.html" %}
{% block title %}Nova proposta | Gestão de Acessos{% endblock %}
{% block head %}<link rel="stylesheet" href="{{ url_for('static', path='/proposals.css') }}">{% endblock %}
{% block content %}
<a href="/portal/propostas">Voltar</a><h1>Nova proposta</h1>
<form method="post" id="proposalCreateForm">
<input type="hidden" name="access_selection_present" value="1">
<section class="form-card proposal-create">
<label>Nome<input name="name" required maxlength="180"></label>
<label>Departamento<select name="department_id" required>{% for d in departments %}<option value="{{ d.id }}">{{ d.nome }}</option>{% endfor %}</select></label>
<label>Base da proposta<select name="origin" id="origin" required><option value="COPIADO_DE_PERFIL">Copiar perfil</option><option value="CONSOLIDADO_FUNCIONARIO">Consolidado de funcionário</option></select></label>
<label data-source="profile">Perfil base<select name="source_profile_id" id="sourceProfile"><option value="">Selecione o perfil</option>{% for p in profiles %}<option value="{{ p.id }}">{{ p.nome }}</option>{% endfor %}</select></label>
<label data-source="employee">Funcionário base<select name="source_employee_id" id="sourceEmployee"><option value="">Selecione o funcionário</option>{% for e in employees %}<option value="{{ e.id }}">{{ e.nome }}</option>{% endfor %}</select></label>
<label class="span-2">Descrição<textarea name="description"></textarea></label><label class="span-2">Justificativa<textarea name="justification"></textarea></label>
</section>
<div class="proposal-base-note" id="baseNote">Selecione o perfil que deseja copiar. Os acessos desse perfil serão marcados automaticamente e poderão ser alterados.</div>
<section class="proposal-editor">
<div class="proposal-tree"><div class="tree-toolbar"><input id="accessSearch" placeholder="Pesquisar caminho, tela ou botão"><label><input id="onlySelected" type="checkbox"> Somente selecionados</label></div><div id="accessTree">
{% set ns=namespace(group='') %}{% for a in accesses %}{% if ns.group != a.caminho_completo %}{% if ns.group %}</div></details>{% endif %}<details open class="tree-group"><summary><input class="group-check" type="checkbox"> {{ a.caminho_completo }}</summary><div>{% set ns.group=a.caminho_completo %}{% endif %}<label class="tree-row" data-search="{{ (a.caminho_completo ~ ' ' ~ a.tela_final ~ ' ' ~ a.botao)|lower }}"><input type="checkbox" name="access_ids" value="{{ a.id }}" data-screen="{{ a.tela_final }}" data-button="{{ a.botao }}"><span>{{ a.tela_final }}</span><small>{{ a.botao }}</small></label>{% endfor %}{% if ns.group %}</div></details>{% endif %}
</div></div><aside class="proposal-buttons"><h2 id="screenTitle">Botões da tela</h2><p id="buttonHint">Selecione uma tela na árvore.</p><div id="screenButtons"></div></aside>
</section><div class="proposal-save"><button>Criar proposta</button></div></form>
{% endblock %}
{% block scripts %}<script src="{{ url_for('static', path='/proposals.js') }}"></script>{% endblock %}
''',encoding='utf-8')

 js=JS.read_text(encoding='utf-8')
 addon='''\n// CREATE_EDITOR_V1\nconst createForm=document.querySelector('#proposalCreateForm');if(createForm){const profile=document.querySelector('#sourceProfile'),employee=document.querySelector('#sourceEmployee'),note=document.querySelector('#baseNote');function clearAccesses(){document.querySelectorAll('.tree-row input[name="access_ids"]').forEach(x=>x.checked=false);document.querySelectorAll('.group-check').forEach(x=>{x.checked=false;x.indeterminate=false})}function syncGroups(){document.querySelectorAll('.group-check').forEach(g=>{const xs=[...g.closest('details').querySelectorAll('.tree-row input[name="access_ids"]')];g.checked=xs.length>0&&xs.every(x=>x.checked);g.indeterminate=!g.checked&&xs.some(x=>x.checked)})}async function loadBase(){clearAccesses();const isProfile=origin.value==='COPIADO_DE_PERFIL',source=isProfile?profile:employee;if(!source.value){note.textContent=isProfile?'Selecione o perfil que deseja copiar.':'Selecione o funcionário que deseja consolidar.';syncGroups();return}note.textContent='Carregando acessos da base...';try{const response=await fetch(`/portal/propostas/base-acessos?origin=${encodeURIComponent(origin.value)}&source_id=${encodeURIComponent(source.value)}`);if(!response.ok)throw new Error(await response.text());const data=await response.json(),ids=new Set(data.access_ids.map(String));document.querySelectorAll('.tree-row input[name="access_ids"]').forEach(x=>x.checked=ids.has(x.value));syncGroups();note.textContent=`${ids.size} acesso(s) importado(s). Você pode marcar ou desmarcar antes de criar.`}catch(error){note.textContent='Não foi possível carregar os acessos da base.';console.error(error)}}profile.addEventListener('change',loadBase);employee.addEventListener('change',loadBase);origin.addEventListener('change',()=>{clearAccesses();syncGroups();note.textContent=origin.value==='COPIADO_DE_PERFIL'?'Selecione o perfil que deseja copiar.':'Selecione o funcionário que deseja consolidar.'});createForm.addEventListener('submit',e=>{const source=origin.value==='COPIADO_DE_PERFIL'?profile:employee;if(!source.value){e.preventDefault();source.focus();note.textContent=origin.value==='COPIADO_DE_PERFIL'?'Selecione o perfil que deseja copiar.':'Selecione o funcionário que deseja consolidar.'}})}\n'''
 if '// CREATE_EDITOR_V1' not in js: JS.write_text(js+addon,encoding='utf-8',newline='\n')
 css=CSS.read_text(encoding='utf-8')
 if '.proposal-base-note' not in css: CSS.write_text(css+'\n.proposal-base-note{margin:14px 0;padding:11px 13px;background:#eef5ff;border-left:4px solid #1f4e78;border-radius:6px;color:#27415e}\n',encoding='utf-8',newline='\n')
 py_compile.compile(str(AC),doraise=True)
except Exception as exc:
 for p in files: shutil.copy2(backup/p.relative_to(ROOT),p)
 raise SystemExit(f'ERRO: alteração cancelada e arquivos restaurados: {exc}')
print('Editor integrado à criação da proposta.')
print('- A árvore abre na própria tela de criação.')
print('- Perfil/funcionário selecionado carrega somente os acessos marcados na base.')
print('- A seleção pode ser alterada antes de criar.')
print('Backup:',backup)
