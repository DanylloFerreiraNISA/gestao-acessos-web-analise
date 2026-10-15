from __future__ import annotations

import py_compile
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
APP = PROJECT / "app"
BACKEND = APP / "access_control.py"
TEMPLATES = APP / "templates"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / f"backup_fluxo_perfil_aprovado_{STAMP}"


def fail(message: str) -> None:
    raise RuntimeError(message)


def function_block(source: str, route_fragment: str) -> re.Match[str]:
    pattern = re.compile(
        rf"(?ms)^@router\.(?:get|post)\([^\n]*{re.escape(route_fragment)}[^\n]*\)\s*\n"
        rf"def\s+\w+\(.*?(?=^@router\.|\Z)"
    )
    match = pattern.search(source)
    if not match:
        fail(f"Rota nao encontrada: {route_fragment}. Nenhum arquivo foi alterado.")
    return match


def replace_block(source: str, match: re.Match[str], replacement: str, label: str) -> str:
    print(f"[OK] {label}")
    return source[: match.start()] + replacement.rstrip() + "\n\n\n" + source[match.end() :]


def backup(path: Path) -> None:
    if path.exists():
        target = BACKUP / path.relative_to(PROJECT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def restore() -> None:
    if not BACKUP.exists():
        return
    for source in BACKUP.rglob("*"):
        if source.is_file():
            destination = PROJECT / source.relative_to(BACKUP)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


if not BACKEND.exists():
    fail(f"Arquivo nao encontrado: {BACKEND}")

print("\nATUALIZACAO DO FLUXO DE PERFIL APROVADO - V2")
print(f"Projeto: {PROJECT}")
print("Nenhum arquivo CSS sera alterado.\n")

source = BACKEND.read_text(encoding="utf-8-sig")

# 1) Caixa de propostas: oculta fluxos concluidos.
proposal_list = function_block(source, "/portal/propostas'")
block = proposal_list.group(0)
if "workflow_status.not_in" not in block:
    query_line = re.search(
        r"(?m)^(?P<i>\s*)query\s*=\s*select\(ProfileProposal\).*order_by\(ProfileProposal\.created_at\.desc\(\)\)\s*$",
        block,
    )
    if not query_line:
        fail("A consulta da tela inicial de propostas nao foi reconhecida. Nenhum arquivo foi alterado.")
    indent = query_line.group("i")
    replacement = (
        f"{indent}query = (\n"
        f"{indent}    select(ProfileProposal)\n"
        f"{indent}    .options(selectinload(ProfileProposal.department))\n"
        f"{indent}    .where(ProfileProposal.workflow_status.not_in({{'APROVADO', 'PUBLICADO', 'ARQUIVADO'}}))\n"
        f"{indent}    .order_by(ProfileProposal.created_at.desc())\n"
        f"{indent})"
    )
    block = block[: query_line.start()] + replacement + block[query_line.end() :]
    source = source[: proposal_list.start()] + block + source[proposal_list.end() :]
    print("[OK] perfis aprovados saem da caixa de propostas")
else:
    print("[OK] filtro da caixa de propostas ja estava aplicado")

# 2) Aprovar: cria Perfil e copia PerfilAcesso. Procura a rota administrativa, sem depender do nome da funcao.
review = function_block(source, "/admin/propostas/{proposal_id}/{action}")
block = review.group(0)
if "Perfil gerado na proposta" not in block:
    marker = re.search(r"(?m)^(?P<i>\s*)if\s+action\s*==\s*['\"]rejeitar['\"]\s*:\s*$", block)
    if not marker:
        fail("O ponto de aprovacao/rejeicao nao foi reconhecido. Nenhum arquivo foi alterado.")
    indent = marker.group("i")
    approval_code = f"""{indent}if action == 'aprovar':
{indent}    proposal = session.scalar(
{indent}        select(ProfileProposal)
{indent}        .options(selectinload(ProfileProposal.accesses))
{indent}        .where(ProfileProposal.id == proposal_id)
{indent}    )
{indent}    if proposal.imported_result_profile_id is None:
{indent}        existing_profile = session.scalar(
{indent}            select(Perfil).where(func.lower(Perfil.nome) == proposal.name.strip().lower())
{indent}        )
{indent}        if existing_profile:
{indent}            raise HTTPException(409, 'Ja existe um perfil com este nome')
{indent}        generated_profile = Perfil(
{indent}            nome=proposal.name.strip(),
{indent}            situacao='Ativo',
{indent}            departamento_id=proposal.department_id,
{indent}            ultima_atualizacao=datetime.now(timezone.utc),
{indent}        )
{indent}        session.add(generated_profile)
{indent}        session.flush()
{indent}        for proposal_access in proposal.accesses:
{indent}            session.add(PerfilAcesso(
{indent}                perfil_id=generated_profile.id,
{indent}                acesso_id=proposal_access.access_id,
{indent}                status=proposal_access.status or 'Permitido',
{indent}            ))
{indent}        proposal.imported_result_profile_id = generated_profile.id
{indent}    details = ((details.strip() + ' | ') if details.strip() else '') + 'Perfil gerado na proposta'

"""
    block = block[: marker.start()] + approval_code + block[marker.start() :]
    source = source[: review.start()] + block + source[review.end() :]
    print("[OK] aprovacao gera perfil com os acessos selecionados")
else:
    print("[OK] geracao do perfil ja estava aplicada")

# 3) Lista atual de perfis, com filtro especifico "Gerado na proposta".
profiles_route = function_block(source, "/portal/perfis'")
profiles_function = '''@router.get('/portal/perfis', response_class=HTMLResponse)
def portal_profiles(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
    nome: str = '',
    departamento_id: int | None = None,
    situacao: str = '',
    origem: str = '',
):
    nome = nome.strip()
    situacao = situacao.strip()
    origem = origem.strip().upper()
    ti_manager = user.role in {ROLE_ADMIN, ROLE_ANALYST}
    generated_ids = select(ProfileProposal.imported_result_profile_id).where(
        ProfileProposal.imported_result_profile_id.is_not(None)
    )
    query = select(Perfil).options(selectinload(Perfil.departamento)).order_by(Perfil.nome)
    if user.role == ROLE_MANAGER:
        query = query.where(Perfil.id.in_(profile_ids_for_department(session, user.department_id)))
    elif departamento_id:
        query = query.where(Perfil.departamento_id == departamento_id)
    if nome:
        query = query.where(Perfil.nome.ilike(f'%{nome}%'))
    if situacao:
        query = query.where(Perfil.situacao == situacao)
    if origem == 'PROPOSTA':
        query = query.where(Perfil.id.in_(generated_ids))
    elif origem == 'ERP':
        query = query.where(Perfil.id.not_in(generated_ids))
    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if ti_manager else []
    profiles = session.scalars(query).unique().all()
    generated_profile_ids = set(session.scalars(generated_ids).all())
    return templates.TemplateResponse(
        request=request,
        name='portal_profiles.html',
        context={
            'user': user,
            'profiles': profiles,
            'departments': departments,
            'filter_name': nome,
            'filter_department_id': departamento_id,
            'filter_status': situacao,
            'filter_origin': origem,
            'show_department_filter': ti_manager,
            'generated_profile_ids': generated_profile_ids,
        },
    )
'''
source = replace_block(source, profiles_route, profiles_function, "filtro de perfis gerados na proposta")

# 4) Detalhe do perfil e inativacao. O botao Voltar aponta explicitamente para /portal/perfis.
profile_detail = function_block(source, "/portal/perfis/{profile_id}'")
profile_detail_function = '''@router.get('/portal/perfis/{profile_id}', response_class=HTMLResponse)
def portal_profile(request: Request, profile_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    profile = session.scalar(
        select(Perfil)
        .options(selectinload(Perfil.departamento), selectinload(Perfil.acessos).selectinload(PerfilAcesso.acesso))
        .where(Perfil.id == profile_id)
    )
    if not profile:
        raise HTTPException(404, 'Perfil nao encontrado')
    if user.role == ROLE_MANAGER and profile.id not in set(session.scalars(profile_ids_for_department(session, user.department_id)).all()):
        raise HTTPException(403, 'Perfil fora do departamento')
    generated_proposal = session.scalar(
        select(ProfileProposal)
        .where(ProfileProposal.imported_result_profile_id == profile.id)
        .order_by(ProfileProposal.id.desc())
    )
    accesses = sorted(
        profile.acessos,
        key=lambda item: (
            item.acesso.caminho_completo.casefold(),
            item.acesso.tela_final.casefold(),
            item.acesso.botao.casefold(),
        ),
    )
    return templates.TemplateResponse(
        request=request,
        name='portal_profile.html',
        context={
            'user': user,
            'profile': profile,
            'accesses': accesses,
            'generated_proposal': generated_proposal,
            'is_admin': user.role == ROLE_ADMIN,
        },
    )
'''
source = replace_block(source, profile_detail, profile_detail_function, "detalhe atual do perfil com arvore")

# Remove rota de situacao antiga, se existir, para nao duplicar.
old_status = re.search(
    r"(?ms)^@router\.post\([^\n]*/portal/perfis/\{profile_id\}/situacao[^\n]*\)\s*\ndef\s+\w+\(.*?(?=^@router\.|\Z)",
    source,
)
if old_status:
    source = source[: old_status.start()] + source[old_status.end() :]

status_route = '''@router.post('/portal/perfis/{profile_id}/situacao')
def portal_profile_status(
    profile_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
    situacao: Annotated[str, Form()],
):
    profile = session.get(Perfil, profile_id)
    if not profile:
        raise HTTPException(404, 'Perfil nao encontrado')
    if situacao not in {'Ativo', 'Inativo'}:
        raise HTTPException(400, 'Situacao invalida')
    profile.situacao = situacao
    profile.ultima_atualizacao = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f'/portal/perfis/{profile.id}', status_code=303)


'''
insert_at = function_block(source, "/portal/perfis/{profile_id}'").end()
source = source[:insert_at] + "\n\n" + status_route + source[insert_at:]
print("[OK] inativar e reativar perfil")

portal_profiles_html = '''{% extends "base.html" %}
{% block title %}Perfis{% endblock %}
{% block content %}
<section class="page-header"><div><h1>Perfis</h1><p>Consulte os perfis importados do ERP e os gerados nas propostas.</p></div></section>
<form method="get" action="/portal/perfis" class="profile-filters">
  <label>Nome<input type="search" name="nome" value="{{ filter_name }}" placeholder="Pesquisar perfil"></label>
  <label>Situação<select name="situacao"><option value="">Todas</option>{% for status in ['Pendente','Ativo','Inativo'] %}<option value="{{ status }}" {% if filter_status == status %}selected{% endif %}>{{ status }}</option>{% endfor %}</select></label>
  <label>Origem<select name="origem"><option value="">Todas</option><option value="ERP" {% if filter_origin == 'ERP' %}selected{% endif %}>Importado do ERP</option><option value="PROPOSTA" {% if filter_origin == 'PROPOSTA' %}selected{% endif %}>Gerado na proposta</option></select></label>
  {% if show_department_filter %}<label>Departamento<select name="departamento_id"><option value="">Todos</option>{% for department in departments %}<option value="{{ department.id }}" {% if filter_department_id == department.id %}selected{% endif %}>{{ department.nome }}</option>{% endfor %}</select></label>{% endif %}
  <div class="filter-actions"><button type="submit">Filtrar</button><a href="/portal/perfis">Limpar</a></div>
</form>
<div class="table-responsive"><table class="profiles-table">
<thead><tr><th>Perfil</th><th>Situação</th><th>Departamento</th><th>Origem</th><th>Ações</th></tr></thead><tbody>
{% for profile in profiles %}<tr>
<td><a href="/portal/perfis/{{ profile.id }}">{{ profile.nome }}</a></td><td>{{ profile.situacao }}</td><td>{{ profile.departamento.nome if profile.departamento else 'Sem departamento' }}</td>
<td>{% if profile.id in generated_profile_ids %}Gerado na proposta{% else %}Importado do ERP{% endif %}</td><td><a href="/portal/perfis/{{ profile.id }}">Consultar</a></td>
</tr>{% else %}<tr><td colspan="5">Nenhum perfil encontrado.</td></tr>{% endfor %}
</tbody></table></div>
{% endblock %}
'''

portal_profile_html = '''{% extends "base.html" %}
{% block title %}{{ profile.nome }}{% endblock %}
{% block content %}
<section class="page-header"><div><a href="/portal/perfis">← Voltar para perfis</a><h1>{{ profile.nome }}</h1><p>{{ profile.situacao }} · {% if generated_proposal %}Gerado na proposta #{{ generated_proposal.id }}{% else %}Importado do ERP{% endif %}</p></div>
{% if is_admin %}<form method="post" action="/portal/perfis/{{ profile.id }}/situacao"><input type="hidden" name="situacao" value="{{ 'Inativo' if profile.situacao != 'Inativo' else 'Ativo' }}"><button type="submit">{{ 'Inativar perfil' if profile.situacao != 'Inativo' else 'Reativar perfil' }}</button></form>{% endif %}</section>
<section><h2>Árvore de acessos</h2>
{% set ns = namespace(path='', screen='', path_open=false, screen_open=false) %}
{% for item in accesses %}{% set access = item.acesso %}
{% if ns.path != access.caminho_completo %}{% if ns.screen_open %}</ul></details>{% set ns.screen_open = false %}{% endif %}{% if ns.path_open %}</div></details>{% endif %}<details open><summary><strong>{{ access.caminho_completo }}</strong></summary><div>{% set ns.path = access.caminho_completo %}{% set ns.screen = '' %}{% set ns.path_open = true %}{% endif %}
{% if ns.screen != access.tela_final %}{% if ns.screen_open %}</ul></details>{% endif %}<details open><summary>{{ access.tela_final }}</summary><ul>{% set ns.screen = access.tela_final %}{% set ns.screen_open = true %}{% endif %}
<li>{{ access.botao }} <small>({{ item.status }})</small></li>
{% else %}<p>Este perfil não possui acessos cadastrados.</p>{% endfor %}{% if ns.screen_open %}</ul></details>{% endif %}{% if ns.path_open %}</div></details>{% endif %}
</section>{% endblock %}
'''

changed_files = [BACKEND, TEMPLATES / "portal_profiles.html", TEMPLATES / "portal_profile.html"]
for path in changed_files:
    backup(path)

try:
    BACKEND.write_text(source, encoding="utf-8")
    (TEMPLATES / "portal_profiles.html").write_text(portal_profiles_html, encoding="utf-8")
    (TEMPLATES / "portal_profile.html").write_text(portal_profile_html, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("\n[SUCESSO] Atualizacao aplicada e validada.")
print(f"[BACKUP] {BACKUP}")
print("[PRESERVADO] Nenhum CSS ou arquivo de cores foi alterado.")
print("Reinicie o servidor e pressione Ctrl + F5.")
