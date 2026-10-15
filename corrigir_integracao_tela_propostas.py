from pathlib import Path
from datetime import datetime
import shutil, py_compile, re

ROOT=Path.cwd().resolve(); APP=ROOT/'app'; AC=APP/'access_control.py'; T=APP/'templates'; S=APP/'static'
required=[AC,T/'proposals.html',T/'proposal_new.html',T/'proposal_detail.html',S/'portal.css']
missing=[p for p in required if not p.exists()]
if missing: raise SystemExit('ERRO: estrutura incompatível; nada alterado: '+', '.join(map(str,missing)))

# Recupera a versão funcional anterior à tentativa defeituosa, mas reaplica a melhoria em seguida.
backups=sorted([p for p in ROOT.glob('backup_propostas_*') if p.is_dir()],key=lambda p:p.name,reverse=True)
source_backup=next((b for b in backups if all((b/p.relative_to(ROOT)).exists() for p in required)),None)
if not source_backup: raise SystemExit('ERRO: backup_propostas_* completo não encontrado; nada alterado.')

safety=ROOT/f"backup_antes_correcao_propostas_{datetime.now():%Y%m%d_%H%M%S}"
for p in required:
 d=safety/p.relative_to(ROOT); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,d)
js=S/'proposals.js'
if js.exists():
 d=safety/js.relative_to(ROOT); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(js,d)

# Base funcional restaura autenticação, sessão e CSS global; depois aplicamos apenas o módulo.
for p in required:
 shutil.copy2(source_backup/p.relative_to(ROOT),p)
if js.exists(): js.unlink()

text=AC.read_text(encoding='utf-8')
for marker in ['class ProfileProposal(', 'class ProfileProposalAccess(', "@router.get('/portal/propostas'", 'def require_user']:
 if marker not in text: raise SystemExit('ERRO: versão não reconhecida após restauração: '+marker)

# Remove apenas uma eventual versão anterior da integração V2/V3.
text=re.sub(r'\n# PROPOSAL_UI_V[23][\s\S]*\Z','\n',text)
addon=r'''

# PROPOSAL_UI_V3 - integração corrigida, sem alterar login ou sessão
def proposal_for_user(session: Session, user: SystemUser, proposal_id: int):
    proposal=session.scalar(select(ProfileProposal).options(selectinload(ProfileProposal.department),selectinload(ProfileProposal.accesses).selectinload(ProfileProposalAccess.access)).where(ProfileProposal.id==proposal_id))
    if not proposal: raise HTTPException(404,'Proposta nao encontrada')
    enforce_department(user,proposal.department_id)
    return proposal

def proposal_can_edit(user: SystemUser, proposal: ProfileProposal):
    return proposal.created_by_id==user.id and proposal.workflow_status in {'RASCUNHO','DEVOLVIDO','REJEITADO'}

def proposal_can_delete(user: SystemUser, proposal: ProfileProposal):
    return proposal.created_by_id==user.id or user.role in {ROLE_ADMIN,ROLE_ANALYST}

@router.get('/portal/propostas/{proposal_id}/editar',response_class=HTMLResponse)
def proposal_edit_v3(request:Request,proposal_id:int,session:Db,user:Annotated[SystemUser,Depends(require_user)]):
    proposal=proposal_for_user(session,user,proposal_id)
    if not proposal_can_edit(user,proposal): raise HTTPException(403,'A proposta nao pode ser editada neste status')
    accesses=session.scalars(select(Acesso).order_by(Acesso.caminho_completo,Acesso.tela_final,Acesso.botao)).all()
    selected={item.access_id for item in proposal.accesses}
    return templates.TemplateResponse(request=request,name='proposal_edit.html',context={'user':user,'proposal':proposal,'accesses':accesses,'selected':selected})

@router.post('/portal/propostas/{proposal_id}/editar')
def proposal_update_v3(proposal_id:int,session:Db,user:Annotated[SystemUser,Depends(require_user)],name:Annotated[str,Form()],description:Annotated[str,Form()]='',justification:Annotated[str,Form()]='',access_ids:Annotated[list[int]|None,Form()]=None):
    proposal=proposal_for_user(session,user,proposal_id)
    if not proposal_can_edit(user,proposal): raise HTTPException(403,'A proposta nao pode ser editada neste status')
    proposal.name=name.strip(); proposal.description=description.strip() or None; proposal.justification=justification.strip() or None
    ids=set(access_ids or [])
    valid=set(session.scalars(select(Acesso.id).where(Acesso.id.in_(ids or {-1}))).all())
    proposal.accesses.clear(); session.flush()
    proposal.accesses.extend(ProfileProposalAccess(access_id=i,status='Permitido') for i in valid)
    create_history(session,proposal.id,user.id,'PROPOSTA_EDITADA',f'{len(valid)} acessos selecionados')
    session.commit(); return RedirectResponse(f'/portal/propostas/{proposal.id}',status_code=303)

@router.post('/portal/propostas/{proposal_id}/excluir')
def proposal_delete_v3(proposal_id:int,session:Db,user:Annotated[SystemUser,Depends(require_user)],reason:Annotated[str,Form()]=''):
    proposal=proposal_for_user(session,user,proposal_id)
    if not proposal_can_delete(user,proposal): raise HTTPException(403,'Sem permissao para excluir esta proposta')
    if len(reason.strip())<3: raise HTTPException(400,'Informe o motivo da exclusao')
    session.delete(proposal); session.commit()
    return RedirectResponse('/portal/propostas',status_code=303)
'''
AC.write_text(text+addon,encoding='utf-8',newline='\n')

(T/'proposals.html').write_text('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/portal.css"><link rel="stylesheet" href="/static/proposals.css"><title>Propostas</title></head><body>{% include '_portal_nav.html' %}<main><div class="title-row"><div><h1>Propostas</h1><p class="proposal-muted">Solicitações de alteração de acesso.</p></div><a class="primary" href="/portal/propostas/nova">Nova proposta</a></div><section class="proposal-list">{% for p in proposals %}<article class="proposal-item"><div><span class="proposal-status s-{{ p.workflow_status|lower }}">{{ p.workflow_status|replace('_',' ') }}</span><h3><a href="/portal/propostas/{{ p.id }}">{{ p.name }}</a></h3><p>{{ p.department.nome }} · {{ p.origin|replace('_',' ') }}</p></div><div class="proposal-actions"><a href="/portal/propostas/{{ p.id }}">Visualizar</a>{% if p.created_by_id == user.id and p.workflow_status in ['RASCUNHO','DEVOLVIDO','REJEITADO'] %}<a href="/portal/propostas/{{ p.id }}/editar">Editar</a>{% endif %}<button type="button" class="proposal-link danger" data-delete="{{ p.id }}" data-name="{{ p.name }}">Excluir</button></div></article>{% else %}<div class="proposal-empty"><b>Nenhuma proposta encontrada.</b><p>Crie uma proposta para começar.</p></div>{% endfor %}</section></main>{% include '_proposal_delete_dialog.html' %}<script src="/static/proposals.js"></script></body></html>''',encoding='utf-8')

# Criação preserva a rota e os nomes de campos originais; visual usa as classes reais do sistema.
(T/'proposal_new.html').write_text('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/portal.css"><link rel="stylesheet" href="/static/proposals.css"><title>Nova proposta</title></head><body>{% include '_portal_nav.html' %}<main><a href="/portal/propostas">Voltar</a><h1>Nova proposta</h1><form method="post" class="form-card proposal-create"><label>Nome<input name="name" required maxlength="180"></label><label>Departamento<select name="department_id" required>{% for d in departments %}<option value="{{ d.id }}">{{ d.nome }}</option>{% endfor %}</select></label><label>Base da proposta<select name="origin" id="origin"><option value="CRIADO_VAZIO">Criar do zero</option><option value="COPIADO_DE_PERFIL">Copiar perfil</option><option value="CONSOLIDADO_FUNCIONARIO">Consolidar funcionário</option><option value="CONSOLIDADO_DEPARTAMENTO_COMUM">Acessos comuns do departamento</option><option value="CONSOLIDADO_DEPARTAMENTO_UNIAO">União do departamento</option></select></label><label data-source="profile">Perfil base<select name="source_profile_id"><option value="">Selecione</option>{% for p in profiles %}<option value="{{ p.id }}">{{ p.nome }}</option>{% endfor %}</select></label><label data-source="employee">Funcionário base<select name="source_employee_id"><option value="">Selecione</option>{% for e in employees %}<option value="{{ e.id }}">{{ e.nome }}</option>{% endfor %}</select></label><label class="span-2">Descrição<textarea name="description"></textarea></label><label class="span-2">Justificativa<textarea name="justification"></textarea></label><div class="warning span-2">A proposta será criada com a base escolhida. Na tela seguinte, use <b>Editar</b> para marcar telas e botões antes de enviar.</div><div class="span-2 form-actions"><button>Criar proposta</button></div></form></main><script src="/static/proposals.js"></script></body></html>''',encoding='utf-8')

(T/'proposal_edit.html').write_text('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/portal.css"><link rel="stylesheet" href="/static/proposals.css"><title>Editar proposta</title></head><body>{% include '_portal_nav.html' %}<main><a href="/portal/propostas/{{ proposal.id }}">Voltar</a><h1>Editar proposta</h1><form method="post"><section class="form-card proposal-meta"><label>Nome<input name="name" required value="{{ proposal.name }}"></label><label>Departamento<input value="{{ proposal.department.nome }}" disabled></label><label class="span-2">Descrição<textarea name="description">{{ proposal.description or '' }}</textarea></label><label class="span-2">Justificativa<textarea name="justification">{{ proposal.justification or '' }}</textarea></label></section><section class="proposal-editor"><div class="proposal-tree"><div class="tree-toolbar"><input id="accessSearch" placeholder="Pesquisar caminho, tela ou botão"><label><input id="onlySelected" type="checkbox"> Somente selecionados</label></div><div id="accessTree">{% set ns=namespace(group='') %}{% for a in accesses %}{% if ns.group != a.caminho_completo %}{% if ns.group %}</div></details>{% endif %}<details open class="tree-group"><summary><input class="group-check" type="checkbox"> {{ a.caminho_completo }}</summary><div>{% set ns.group=a.caminho_completo %}{% endif %}<label class="tree-row" data-search="{{ (a.caminho_completo ~ ' ' ~ a.tela_final ~ ' ' ~ a.botao)|lower }}"><input type="checkbox" name="access_ids" value="{{ a.id }}" data-screen="{{ a.tela_final }}" data-button="{{ a.botao }}" {% if a.id in selected %}checked{% endif %}><span>{{ a.tela_final }}</span><small>{{ a.botao }}</small></label>{% endfor %}{% if ns.group %}</div></details>{% endif %}</div></div><aside class="proposal-buttons"><h2 id="screenTitle">Botões da tela</h2><p id="buttonHint">Selecione uma tela na árvore.</p><div id="screenButtons"></div></aside></section><div class="proposal-save"><button>Salvar alterações</button></div></form></main><script src="/static/proposals.js"></script></body></html>''',encoding='utf-8')

(T/'proposal_detail.html').write_text('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/portal.css"><link rel="stylesheet" href="/static/proposals.css"><title>{{ proposal.name }}</title></head><body>{% include '_portal_nav.html' %}<main><a href="/portal/propostas">Voltar</a><div class="title-row"><div><h1>{{ proposal.name }}</h1><p>{{ proposal.department.nome }} · <span class="proposal-status s-{{ proposal.workflow_status|lower }}">{{ proposal.workflow_status|replace('_',' ') }}</span></p></div><div class="proposal-actions">{% if proposal.created_by_id == user.id and proposal.workflow_status in ['RASCUNHO','DEVOLVIDO','REJEITADO'] %}<a class="primary" href="/portal/propostas/{{ proposal.id }}/editar">Editar</a>{% endif %}<button type="button" class="proposal-link danger" data-delete="{{ proposal.id }}" data-name="{{ proposal.name }}">Excluir</button></div></div><section class="proposal-panel"><p>{{ proposal.description or '' }}</p><h2>Acessos ({{ proposal.accesses|length }})</h2><div class="access-list">{% for item in proposal.accesses %}<div><span>{{ item.access.caminho_completo }} › {{ item.access.tela_final }} › {{ item.access.botao }}</span><b class="permission {{ item.status|lower }}">{{ item.status }}</b></div>{% else %}<p>Nenhum acesso selecionado.</p>{% endfor %}</div></section>{% if proposal.created_by_id == user.id and proposal.workflow_status in ['RASCUNHO','DEVOLVIDO','REJEITADO'] %}<form method="post" action="/portal/propostas/{{ proposal.id }}/enviar"><button>Enviar para T.I.</button></form>{% endif %}{% if user.role in ['ADMIN_TI','ANALISTA_TI'] and proposal.workflow_status == 'EM_REVISAO' %}<section class="review">{% for action,label in [('aprovar','Aprovar'),('devolver','Devolver'),('rejeitar','Rejeitar')] %}<form method="post" action="/admin/propostas/{{ proposal.id }}/{{ action }}"><textarea name="details" placeholder="Parecer ou motivo"></textarea><button>{{ label }}</button></form>{% endfor %}</section>{% endif %}</main>{% include '_proposal_delete_dialog.html' %}<script src="/static/proposals.js"></script></body></html>''',encoding='utf-8')

(T/'_proposal_delete_dialog.html').write_text('''<dialog id="deleteDialog"><form method="post" id="deleteForm"><h3>Excluir proposta</h3><p id="deleteText"></p><label>Motivo<textarea name="reason" required minlength="3"></textarea></label><div class="dialog-actions"><button type="button" data-close>Cancelar</button><button class="danger-button">Excluir proposta</button></div></form></dialog>''',encoding='utf-8')

(S/'proposals.css').write_text('''.proposal-muted{color:#65758b}.proposal-list{display:grid;gap:12px}.proposal-item,.proposal-panel,.proposal-tree,.proposal-buttons{background:#fff;border:1px solid #d7e0e8;border-radius:9px;padding:16px}.proposal-item{display:flex;justify-content:space-between;gap:16px}.proposal-item h3{margin:8px 0}.proposal-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.proposal-link{border:0;background:transparent;color:#1f4e78;padding:4px}.danger{color:#b42318}.proposal-status{display:inline-block;padding:4px 8px;border-radius:999px;background:#e7edf3;font-size:12px}.s-aprovado{background:#dcfae6}.s-rejeitado{background:#fee4e2}.s-em_revisao{background:#fef0c7}.proposal-empty{text-align:center;background:#fff;border-radius:9px;padding:32px}.proposal-create,.proposal-meta{max-width:none!important;grid-template-columns:1fr 1fr!important}.span-2{grid-column:1/-1}.form-actions{text-align:right}.proposal-editor{display:grid;grid-template-columns:minmax(480px,1fr) minmax(300px,.55fr);gap:16px;margin-top:16px}.tree-toolbar{display:flex;gap:12px;align-items:center;margin-bottom:12px}.tree-toolbar>input{flex:1;padding:9px}.tree-toolbar label{display:flex;align-items:center;gap:6px}.tree-group{padding:7px;border-bottom:1px solid #edf0f2}.tree-group summary{font-weight:700;cursor:pointer}.tree-row{display:grid;grid-template-columns:auto 1fr auto;gap:9px;align-items:center;padding:8px 10px;margin-left:20px;border-bottom:1px solid #f0f2f4;cursor:pointer}.proposal-buttons{align-self:start;position:sticky;top:12px}.proposal-buttons>div{display:grid;gap:10px}.button-check{display:flex;align-items:center;gap:7px}.proposal-save{position:sticky;bottom:0;background:#fff;border-top:1px solid #d7e0e8;padding:12px;text-align:right;margin-top:12px}dialog{border:0;border-radius:10px;box-shadow:0 18px 50px #0003;width:min(450px,92vw)}dialog label{display:grid;gap:6px}dialog textarea{min-height:85px}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}.danger-button{background:#b42318}.hidden-source{display:none!important}@media(max-width:850px){.proposal-create,.proposal-meta,.proposal-editor{grid-template-columns:1fr!important}.span-2{grid-column:auto}.proposal-item{flex-direction:column}.tree-toolbar{align-items:stretch;flex-direction:column}}''',encoding='utf-8')

(S/'proposals.js').write_text('''document.querySelectorAll('[data-delete]').forEach(b=>b.addEventListener('click',()=>{const d=document.querySelector('#deleteDialog');document.querySelector('#deleteForm').action=`/portal/propostas/${b.dataset.delete}/excluir`;document.querySelector('#deleteText').textContent=`Deseja excluir “${b.dataset.name}”?`;d.showModal()}));document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());const origin=document.querySelector('#origin');function sourceFields(){if(!origin)return;const v=origin.value;document.querySelectorAll('[data-source]').forEach(x=>x.classList.toggle('hidden-source',(x.dataset.source==='profile'&&v!=='COPIADO_DE_PERFIL')||(x.dataset.source==='employee'&&v!=='CONSOLIDADO_FUNCIONARIO')))}if(origin){origin.onchange=sourceFields;sourceFields()}const search=document.querySelector('#accessSearch'),only=document.querySelector('#onlySelected');function filterTree(){document.querySelectorAll('.tree-row').forEach(r=>r.hidden=!r.dataset.search.includes((search?.value||'').toLowerCase())||(only?.checked&&!r.querySelector('input').checked))}if(search)search.oninput=filterTree;if(only)only.onchange=filterTree;document.querySelectorAll('.group-check').forEach(g=>g.onchange=()=>g.closest('details').querySelectorAll('.tree-row input').forEach(x=>x.checked=g.checked));document.querySelectorAll('.tree-row').forEach(r=>r.addEventListener('click',()=>{const source=r.querySelector('input'),screen=source.dataset.screen,title=document.querySelector('#screenTitle'),box=document.querySelector('#screenButtons');title.textContent=screen;document.querySelector('#buttonHint').hidden=true;box.innerHTML='';document.querySelectorAll('.tree-row input').forEach(i=>{if(i.dataset.screen!==screen)return;const label=document.createElement('label');label.className='button-check';const check=document.createElement('input');check.type='checkbox';check.checked=i.checked;check.onchange=()=>i.checked=check.checked;label.append(check,document.createTextNode(i.dataset.button));box.append(label)})}));''',encoding='utf-8')

try:
 py_compile.compile(str(AC),doraise=True)
except Exception:
 for p in required:
  shutil.copy2(safety/p.relative_to(ROOT),p)
 for extra in [T/'proposal_edit.html',T/'_proposal_delete_dialog.html',S/'proposals.css',S/'proposals.js']:
  if extra.exists(): extra.unlink()
 raise
print('Correção integrada aplicada com sucesso.')
print('Backup de segurança:',safety)
print('Base funcional usada:',source_backup)
