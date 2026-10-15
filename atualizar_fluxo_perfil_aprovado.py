from __future__ import annotations

import py_compile
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

FILES = [
    BACKEND,
    TEMPLATES / "portal_profiles.html",
    TEMPLATES / "portal_profile.html",
]


def stop(message: str) -> None:
    raise RuntimeError(message)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[OK] {label} ja estava aplicado")
        return text
    count = text.count(old)
    if count != 1:
        stop(f"Nao foi possivel aplicar '{label}'. Ocorrencias encontradas: {count}")
    print(f"[OK] {label}")
    return text.replace(old, new, 1)


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    relative = path.relative_to(PROJECT)
    destination = BACKUP / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


if not BACKEND.exists():
    stop(f"Arquivo nao encontrado: {BACKEND}")

print("\nATUALIZACAO DO FLUXO DE PERFIL APROVADO")
print(f"Projeto: {PROJECT}")
print("Esta atualizacao nao altera arquivos CSS nem as cores do sistema.\n")

backend = BACKEND.read_text(encoding="utf-8-sig")

# 1. Remove propostas aprovadas/publicadas da caixa principal.
old_proposals = """    query = select(ProfileProposal).options(selectinload(ProfileProposal.department)).order_by(ProfileProposal.created_at.desc())
    if user.role == ROLE_MANAGER: query = query.where(ProfileProposal.department_id == user.department_id)
"""
new_proposals = """    query = (
        select(ProfileProposal)
        .options(selectinload(ProfileProposal.department))
        .where(ProfileProposal.workflow_status.not_in({'APROVADO', 'PUBLICADO', 'ARQUIVADO'}))
        .order_by(ProfileProposal.created_at.desc())
    )
    if user.role == ROLE_MANAGER:
        query = query.where(ProfileProposal.department_id == user.department_id)
"""
backend = replace_once(backend, old_proposals, new_proposals, "ocultar propostas concluidas da caixa inicial")

# 2. Ao aprovar, cria o perfil definitivo e copia os acessos da proposta.
old_approval = """    proposal.workflow_status = mapping[action]
    proposal.reviewed_by_id = user.id
    proposal.reviewed_at = datetime.now(timezone.utc)
    if action == 'rejeitar':
"""
new_approval = """    proposal.workflow_status = mapping[action]
    proposal.reviewed_by_id = user.id
    proposal.reviewed_at = datetime.now(timezone.utc)

    if action == 'aprovar':
        proposal = session.scalar(
            select(ProfileProposal)
            .options(selectinload(ProfileProposal.accesses))
            .where(ProfileProposal.id == proposal_id)
        )
        if proposal.imported_result_profile_id is None:
            duplicated = session.scalar(select(Perfil).where(func.lower(Perfil.nome) == proposal.name.strip().lower()))
            if duplicated:
                raise HTTPException(409, 'Ja existe um perfil com este nome')
            generated_profile = Perfil(
                nome=proposal.name.strip(),
                situacao='Ativo',
                departamento_id=proposal.department_id,
                ultima_atualizacao=datetime.now(timezone.utc),
            )
            session.add(generated_profile)
            session.flush()
            for item in proposal.accesses:
                session.add(PerfilAcesso(
                    perfil_id=generated_profile.id,
                    acesso_id=item.access_id,
                    status=item.status or 'Permitido',
                ))
            proposal.imported_result_profile_id = generated_profile.id
        details = (details.strip() + ' | ' if details.strip() else '') + 'Perfil gerado na proposta'

    if action == 'rejeitar':
"""
backend = replace_once(backend, old_approval, new_approval, "gerar perfil e acessos na aprovacao")

# 3. Melhora a rota de detalhe para carregar a arvore e garantir volta ao portal atual.
old_detail = """@router.get('/portal/perfis/{profile_id}', response_class=HTMLResponse)
def portal_profile(request: Request, profile_id: int, session: Db, user: Annotated[SystemUser, Depends(require_user)]):
    profile = session.scalar(select(Perfil).options(selectinload(Perfil.departamento), selectinload(Perfil.acessos).selectinload(PerfilAcesso.acesso)).where(Perfil.id == profile_id))
    if not profile: raise HTTPException(404, 'Perfil nao encontrado')
    if user.role == ROLE_MANAGER and profile.id not in set(session.scalars(profile_ids_for_department(session, user.department_id)).all()): raise HTTPException(403, 'Perfil fora do departamento')
    return templates.TemplateResponse(request=request, name='portal_profile.html', context={'user': user, 'profile': profile})
"""
new_detail = """@router.get('/portal/perfis/{profile_id}', response_class=HTMLResponse)
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
    ordered_accesses = sorted(
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
            'ordered_accesses': ordered_accesses,
            'generated_proposal': generated_proposal,
            'is_admin': user.role == ROLE_ADMIN,
        },
    )


@router.post('/portal/perfis/{profile_id}/situacao')
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
"""
backend = replace_once(backend, old_detail, new_detail, "arvore e inativacao do perfil")

# Templates completos, usando apenas classes existentes e estilos inline neutros.
portal_profiles = '''{% extends "base.html" %}
{% block title %}Perfis{% endblock %}
{% block content %}
<section class="page-header">
  <div><h1>Perfis</h1><p>Consulte os perfis importados do ERP e os gerados pelas propostas.</p></div>
</section>
<form method="get" action="/portal/perfis" class="profile-filters">
  <label>Nome<input type="search" name="nome" value="{{ filter_name }}" placeholder="Pesquisar perfil"></label>
  <label>Situação<select name="situacao"><option value="">Todas</option>{% for status in ['Pendente','Ativo','Inativo'] %}<option value="{{ status }}" {% if filter_status == status %}selected{% endif %}>{{ status }}</option>{% endfor %}</select></label>
  <label>Origem<select name="origem"><option value="">Todas</option><option value="ERP" {% if filter_origin == 'ERP' %}selected{% endif %}>Importado do ERP</option><option value="SISTEMA" {% if filter_origin == 'SISTEMA' %}selected{% endif %}>Gerado na proposta</option></select></label>
  {% if show_department_filter %}<label>Departamento<select name="departamento_id"><option value="">Todos</option>{% for department in departments %}<option value="{{ department.id }}" {% if filter_department_id == department.id %}selected{% endif %}>{{ department.nome }}</option>{% endfor %}</select></label>{% endif %}
  <div class="filter-actions"><button type="submit">Filtrar</button><a href="/portal/perfis">Limpar</a></div>
</form>
<div class="table-responsive">
<table class="profiles-table">
<thead><tr><th>Perfil</th><th>Situação</th><th>Departamento</th><th>Origem</th><th>Ações</th></tr></thead>
<tbody>
{% for profile in profiles %}
<tr>
  <td><a href="/portal/perfis/{{ profile.id }}">{{ profile.nome }}</a></td>
  <td>{{ profile.situacao }}</td>
  <td>{{ profile.departamento.nome if profile.departamento else 'Sem departamento' }}</td>
  <td>{% if profile.id in system_profile_ids %}<strong>Gerado na proposta</strong>{% else %}Importado do ERP{% endif %}</td>
  <td><a href="/portal/perfis/{{ profile.id }}">Consultar</a></td>
</tr>
{% else %}<tr><td colspan="5">Nenhum perfil encontrado.</td></tr>{% endfor %}
</tbody>
</table>
</div>
{% endblock %}
'''

portal_profile = '''{% extends "base.html" %}
{% block title %}{{ profile.nome }}{% endblock %}
{% block content %}
<section class="page-header">
  <div>
    <a href="/portal/perfis">← Voltar para perfis</a>
    <h1>{{ profile.nome }}</h1>
    <p>{{ profile.situacao }} · {% if generated_proposal %}Gerado na proposta #{{ generated_proposal.id }}{% else %}Importado do ERP{% endif %}</p>
  </div>
  {% if is_admin %}
  <form method="post" action="/portal/perfis/{{ profile.id }}/situacao">
    <input type="hidden" name="situacao" value="{{ 'Inativo' if profile.situacao != 'Inativo' else 'Ativo' }}">
    <button type="submit">{{ 'Inativar perfil' if profile.situacao != 'Inativo' else 'Reativar perfil' }}</button>
  </form>
  {% endif %}
</section>
<section>
  <h2>Árvore de acessos</h2>
  {% set ns = namespace(path='', screen='', path_open=false, screen_open=false) %}
  {% for item in ordered_accesses %}
    {% set access = item.acesso %}
    {% if ns.path != access.caminho_completo %}
      {% if ns.screen_open %}</ul></details>{% set ns.screen_open = false %}{% endif %}
      {% if ns.path_open %}</div></details>{% endif %}
      <details open><summary><strong>{{ access.caminho_completo }}</strong></summary><div style="padding-left: 1.25rem;">
      {% set ns.path = access.caminho_completo %}{% set ns.screen = '' %}{% set ns.path_open = true %}
    {% endif %}
    {% if ns.screen != access.tela_final %}
      {% if ns.screen_open %}</ul></details>{% endif %}
      <details open><summary>{{ access.tela_final }}</summary><ul>
      {% set ns.screen = access.tela_final %}{% set ns.screen_open = true %}
    {% endif %}
    <li>{{ access.botao }} <small>({{ item.status }})</small></li>
  {% else %}<p>Este perfil não possui acessos cadastrados.</p>{% endfor %}
  {% if ns.screen_open %}</ul></details>{% endif %}
  {% if ns.path_open %}</div></details>{% endif %}
</section>
{% endblock %}
'''

for file in FILES:
    backup_file(file)

try:
    BACKEND.write_text(backend, encoding="utf-8")
    (TEMPLATES / "portal_profiles.html").write_text(portal_profiles, encoding="utf-8")
    (TEMPLATES / "portal_profile.html").write_text(portal_profile, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    for source in BACKUP.rglob("*"):
        if source.is_file():
            target = PROJECT / source.relative_to(BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    raise

print("\n[SUCESSO] Atualizacao aplicada e backend validado.")
print(f"[BACKUP] {BACKUP}")
print("[ALTERADO] app/access_control.py")
print("[ALTERADO] app/templates/portal_profiles.html")
print("[ALTERADO] app/templates/portal_profile.html")
print("[PRESERVADO] Nenhum CSS foi alterado.")
print("\nReinicie o servidor e pressione Ctrl + F5 no navegador.")
