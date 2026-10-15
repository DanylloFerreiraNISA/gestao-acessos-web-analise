from __future__ import annotations
import py_compile, re, shutil, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
APP = ROOT / 'app'; BACKEND = APP / 'access_control.py'; TPL = APP / 'templates'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
BACKUP = ROOT / f'backup_fluxo_perfil_aprovado_{STAMP}'
CHANGED = [BACKEND, TPL/'portal_profiles.html', TPL/'portal_profile.html']

def die(msg): raise RuntimeError(msg)
def backup():
    for p in CHANGED:
        if p.exists():
            d=BACKUP/p.relative_to(ROOT); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,d)
def restore():
    if BACKUP.exists():
        for p in BACKUP.rglob('*'):
            if p.is_file():
                d=ROOT/p.relative_to(BACKUP); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,d)
def route_block(src, route, method=None):
    mth = method or '(?:get|post)'
    pat=re.compile(rf'(?ms)^@router\.{mth}\([^\n]*{re.escape(route)}[^\n]*\)\s*\ndef\s+\w+\(.*?(?=^@router\.|\Z)')
    m=pat.search(src)
    if not m: die(f'Rota nao encontrada: {route}')
    return m

def replace_block(src,m,new): return src[:m.start()]+new.rstrip()+'\n\n\n'+src[m.end():]

if not BACKEND.exists(): die(f'Arquivo nao encontrado: {BACKEND}')
print('\nATUALIZACAO DO FLUXO DE PERFIL APROVADO - V4')
print(f'Projeto: {ROOT}')
print('Nenhum CSS ou cor sera alterado.\n')
src=BACKEND.read_text(encoding='utf-8-sig')

# 1. Oculta propostas concluidas.
m=route_block(src,"/portal/propostas'",'get'); b=m.group(0)
if 'workflow_status.not_in' not in b:
    q=re.search(r'(?m)^(?P<i>\s*)query\s*=\s*select\(ProfileProposal\).*order_by\(ProfileProposal\.created_at\.desc\(\)\)\s*$',b)
    if not q: die('Consulta da lista de propostas nao reconhecida.')
    i=q.group('i'); nq=(f"{i}query = (\n{i}    select(ProfileProposal)\n{i}    .options(selectinload(ProfileProposal.department))\n"
        f"{i}    .where(ProfileProposal.workflow_status.not_in({{'APROVADO', 'PUBLICADO', 'ARQUIVADO'}}))\n"
        f"{i}    .order_by(ProfileProposal.created_at.desc())\n{i})")
    b=b[:q.start()]+nq+b[q.end():]; src=src[:m.start()]+b+src[m.end():]
print('[OK] aprovados removidos da tela inicial de propostas')

# 2. Localiza funcao administrativa pelo mapping, sem depender de reviewed_at.
if 'Perfil gerado na proposta' not in src:
    mp=src.find("mapping = {'aprovar':")
    if mp<0: mp=src.find('mapping = {"aprovar":')
    if mp<0: die('Mapeamento aprovar/rejeitar/devolver nao encontrado.')
    fs=src.rfind('\ndef ',0,mp); fe=src.find('\n@router.',mp)
    if fs<0: die('Funcao administrativa nao localizada.')
    if fe<0: fe=len(src)
    b=src[fs:fe]
    # Insere antes do primeiro bloco de rejeicao. Aceita linha completa ou bloco.
    marker=re.search(r'(?m)^(?P<i>\s*)if\s+action\s*==\s*[\'\"]rejeitar[\'\"]\s*:',b)
    if not marker:
        # fallback: insere antes de create_history/commit, depois da atribuicao de status
        marker=re.search(r'(?m)^(?P<i>\s*)create_history\(',b)
    if not marker: die('Ponto seguro para inserir a aprovacao nao encontrado.')
    i=marker.group('i')
    code=f"""{i}if action == 'aprovar':
{i}    proposal = session.scalar(select(ProfileProposal).options(selectinload(ProfileProposal.accesses)).where(ProfileProposal.id == proposal_id))
{i}    if proposal.imported_result_profile_id is None:
{i}        existing = session.scalar(select(Perfil).where(func.lower(Perfil.nome) == proposal.name.strip().lower()))
{i}        if existing:
{i}            raise HTTPException(409, 'Ja existe um perfil com este nome')
{i}        generated = Perfil(nome=proposal.name.strip(), situacao='Ativo', departamento_id=proposal.department_id, ultima_atualizacao=datetime.now(timezone.utc))
{i}        session.add(generated)
{i}        session.flush()
{i}        for pa in proposal.accesses:
{i}            session.add(PerfilAcesso(perfil_id=generated.id, acesso_id=pa.access_id, status=pa.status or 'Permitido'))
{i}        proposal.imported_result_profile_id = generated.id
{i}    details = ((details.strip() + ' | ') if details.strip() else '') + 'Perfil gerado na proposta'

"""
    b=b[:marker.start()]+code+b[marker.start():]; src=src[:fs]+b+src[fe:]
print('[OK] aprovacao gera perfil e copia acessos')

# 3. Lista de perfis com filtro Gerado na proposta.
m=route_block(src,"/portal/perfis'",'get')
new_list="""@router.get('/portal/perfis', response_class=HTMLResponse)
def portal_profiles(request: Request, session: Db, user: Annotated[SystemUser, Depends(require_user)], nome: str = '', departamento_id: int | None = None, situacao: str = '', origem: str = ''):
    nome, situacao, origem = nome.strip(), situacao.strip(), origem.strip().upper()
    ti = user.role in {ROLE_ADMIN, ROLE_ANALYST}
    generated_ids = select(ProfileProposal.imported_result_profile_id).where(ProfileProposal.imported_result_profile_id.is_not(None))
    query = select(Perfil).options(selectinload(Perfil.departamento)).order_by(Perfil.nome)
    if user.role == ROLE_MANAGER:
        query = query.where(Perfil.id.in_(profile_ids_for_department(session, user.department_id)))
    elif departamento_id:
        query = query.where(Perfil.departamento_id == departamento_id)
    if nome: query = query.where(Perfil.nome.ilike(f'%{nome}%'))
    if situacao: query = query.where(Perfil.situacao == situacao)
    if origem == 'PROPOSTA': query = query.where(Perfil.id.in_(generated_ids))
    elif origem == 'ERP': query = query.where(Perfil.id.not_in(generated_ids))
    return templates.TemplateResponse(request=request, name='portal_profiles.html', context={
        'user':user, 'profiles':session.scalars(query).unique().all(),
        'departments':session.scalars(select(Departamento).order_by(Departamento.nome)).all() if ti else [],
        'filter_name':nome, 'filter_department_id':departamento_id, 'filter_status':situacao,
        'filter_origin':origem, 'show_department_filter':ti,
        'generated_profile_ids':set(session.scalars(generated_ids).all()),
    })
"""
src=replace_block(src,m,new_list); print('[OK] filtro Gerado na proposta adicionado')

# 4. Detalhe atual, arvore, voltar correto.
m=route_block(src,"/portal/perfis/{profile_id}'",'get')
new_detail="""@router.get('/portal/perfis/{profile_id}', response_class=HTMLResponse)
def portal_profile(request: Request, profile_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    profile=session.scalar(select(Perfil).options(selectinload(Perfil.departamento),selectinload(Perfil.acessos).selectinload(PerfilAcesso.acesso)).where(Perfil.id==profile_id))
    if not profile: raise HTTPException(404,'Perfil nao encontrado')
    if user.role==ROLE_MANAGER and profile.id not in set(session.scalars(profile_ids_for_department(session,user.department_id)).all()): raise HTTPException(403,'Perfil fora do departamento')
    proposal=session.scalar(select(ProfileProposal).where(ProfileProposal.imported_result_profile_id==profile.id).order_by(ProfileProposal.id.desc()))
    accesses=sorted(profile.acessos,key=lambda x:(x.acesso.caminho_completo.casefold(),x.acesso.tela_final.casefold(),x.acesso.botao.casefold()))
    return templates.TemplateResponse(request=request,name='portal_profile.html',context={'user':user,'profile':profile,'accesses':accesses,'generated_proposal':proposal,'is_admin':user.role==ROLE_ADMIN})
"""
src=replace_block(src,m,new_detail)
# remove route antiga de situacao se houver
old=re.search(r'(?ms)^@router\.post\([^\n]*/portal/perfis/\{profile_id\}/situacao[^\n]*\)\s*\ndef\s+\w+\(.*?(?=^@router\.|\Z)',src)
if old: src=src[:old.start()]+src[old.end():]
insert=route_block(src,"/portal/perfis/{profile_id}'",'get').end()
status="""

@router.post('/portal/perfis/{profile_id}/situacao')
def portal_profile_status(profile_id:int, session:Db, user:Annotated[SystemUser,Depends(require_admin)], situacao:Annotated[str,Form()]):
    profile=session.get(Perfil,profile_id)
    if not profile: raise HTTPException(404,'Perfil nao encontrado')
    if situacao not in {'Ativo','Inativo'}: raise HTTPException(400,'Situacao invalida')
    profile.situacao=situacao; profile.ultima_atualizacao=datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f'/portal/perfis/{profile.id}',status_code=303)
"""
src=src[:insert]+status+src[insert:]; print('[OK] arvore, voltar, inativar e reativar')

profiles_html='''{% extends "base.html" %}{% block title %}Perfis{% endblock %}{% block content %}
<section class="page-header"><div><h1>Perfis</h1><p>Perfis importados do ERP e gerados nas propostas.</p></div></section>
<form method="get" action="/portal/perfis" class="profile-filters"><label>Nome<input name="nome" value="{{ filter_name }}"></label><label>Situação<select name="situacao"><option value="">Todas</option>{% for s in ['Pendente','Ativo','Inativo'] %}<option value="{{s}}" {% if filter_status==s %}selected{% endif %}>{{s}}</option>{% endfor %}</select></label><label>Origem<select name="origem"><option value="">Todas</option><option value="ERP" {% if filter_origin=='ERP' %}selected{% endif %}>Importado do ERP</option><option value="PROPOSTA" {% if filter_origin=='PROPOSTA' %}selected{% endif %}>Gerado na proposta</option></select></label>{% if show_department_filter %}<label>Departamento<select name="departamento_id"><option value="">Todos</option>{% for d in departments %}<option value="{{d.id}}" {% if filter_department_id==d.id %}selected{% endif %}>{{d.nome}}</option>{% endfor %}</select></label>{% endif %}<button>Filtrar</button><a href="/portal/perfis">Limpar</a></form>
<div class="table-responsive"><table class="profiles-table"><thead><tr><th>Perfil</th><th>Situação</th><th>Departamento</th><th>Origem</th><th>Ação</th></tr></thead><tbody>{% for p in profiles %}<tr><td><a href="/portal/perfis/{{p.id}}">{{p.nome}}</a></td><td>{{p.situacao}}</td><td>{{p.departamento.nome if p.departamento else 'Sem departamento'}}</td><td>{% if p.id in generated_profile_ids %}Gerado na proposta{% else %}Importado do ERP{% endif %}</td><td><a href="/portal/perfis/{{p.id}}">Consultar</a></td></tr>{% else %}<tr><td colspan="5">Nenhum perfil encontrado.</td></tr>{% endfor %}</tbody></table></div>{% endblock %}'''
profile_html='''{% extends "base.html" %}{% block title %}{{profile.nome}}{% endblock %}{% block content %}<section class="page-header"><div><a href="/portal/perfis">← Voltar para perfis</a><h1>{{profile.nome}}</h1><p>{{profile.situacao}} · {% if generated_proposal %}Gerado na proposta #{{generated_proposal.id}}{% else %}Importado do ERP{% endif %}</p></div>{% if is_admin %}<form method="post" action="/portal/perfis/{{profile.id}}/situacao"><input type="hidden" name="situacao" value="{{'Inativo' if profile.situacao!='Inativo' else 'Ativo'}}"><button>{{'Inativar perfil' if profile.situacao!='Inativo' else 'Reativar perfil'}}</button></form>{% endif %}</section><section><h2>Árvore de acessos</h2>{% set ns=namespace(path='',screen='',po=false,so=false) %}{% for item in accesses %}{% set a=item.acesso %}{% if ns.path!=a.caminho_completo %}{% if ns.so %}</ul></details>{% set ns.so=false %}{% endif %}{% if ns.po %}</div></details>{% endif %}<details open><summary><strong>{{a.caminho_completo}}</strong></summary><div>{% set ns.path=a.caminho_completo %}{% set ns.screen='' %}{% set ns.po=true %}{% endif %}{% if ns.screen!=a.tela_final %}{% if ns.so %}</ul></details>{% endif %}<details open><summary>{{a.tela_final}}</summary><ul>{% set ns.screen=a.tela_final %}{% set ns.so=true %}{% endif %}<li>{{a.botao}} <small>({{item.status}})</small></li>{% else %}<p>Sem acessos.</p>{% endfor %}{% if ns.so %}</ul></details>{% endif %}{% if ns.po %}</div></details>{% endif %}</section>{% endblock %}'''

backup()
try:
    BACKEND.write_text(src,encoding='utf-8'); TPL.mkdir(parents=True,exist_ok=True)
    (TPL/'portal_profiles.html').write_text(profiles_html,encoding='utf-8')
    (TPL/'portal_profile.html').write_text(profile_html,encoding='utf-8')
    py_compile.compile(str(BACKEND),doraise=True)
except Exception:
    restore(); raise
print(f'\n[SUCESSO] Atualizacao aplicada. Backup: {BACKUP}')
print('[PRESERVADO] Nenhum CSS foi alterado. Reinicie o servidor e pressione Ctrl + F5.')
