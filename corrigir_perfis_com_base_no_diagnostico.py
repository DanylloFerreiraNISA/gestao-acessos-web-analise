from __future__ import annotations

import py_compile
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
APP = ROOT / "app"
BACKEND = APP / "access_control.py"
TPL = APP / "templates"
BASE = TPL / "base.html"
LIST = TPL / "portal_profiles.html"
DETAIL = TPL / "portal_profile.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_correcao_perfis_diagnostico_{STAMP}"
FILES = [BACKEND, BASE, LIST, DETAIL]

for path in FILES:
    if not path.exists():
        raise RuntimeError(f"Arquivo necessario nao encontrado: {path}")


def route_block(source: str, route: str, method: str):
    pattern = re.compile(
        rf"(?ms)^@router\.{method}\([^\n]*{re.escape(route)}[^\n]*\)\s*\n"
        rf"def\s+\w+\(.*?(?=^@router\.|\Z)"
    )
    return pattern.search(source)


def replace_route(source: str, route: str, method: str, replacement: str) -> str:
    match = route_block(source, route, method)
    if not match:
        raise RuntimeError(f"Rota nao encontrada: {method.upper()} {route}")
    return source[:match.start()] + replacement.rstrip() + "\n\n\n" + source[match.end():]


def remove_route_if_exists(source: str, route: str, method: str) -> str:
    while True:
        match = route_block(source, route, method)
        if not match:
            return source
        source = source[:match.start()] + source[match.end():]


def backup(path: Path):
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def restore():
    for source in BACKUP.rglob("*"):
        if source.is_file():
            target = ROOT / source.relative_to(BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


print("\nCORRECAO DE PERFIS BASEADA NO DIAGNOSTICO REAL")
print(f"Projeto: {ROOT}")
print("Padrao escolhido: portal_profiles.html, igual a tela enviada na imagem.")
print("Nenhum CSS sera alterado.\n")

source = BACKEND.read_text(encoding="utf-8-sig")

# Remove bloco de APIs inserido pela tentativa anterior. As rotas serão recriadas abaixo.
for marker in ("# PERFIS_PADRAO_PROPOSTA_V2", "# PERFIS_PROPOSTA_PADRAO_V1"):
    pos = source.find(marker)
    if pos >= 0:
        source = source[:pos].rstrip() + "\n"

list_route = '''@router.get('/portal/perfis', response_class=HTMLResponse)
def portal_profiles(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
    nome: str = '',
    departamento_id: int | None = None,
    origem: str = '',
):
    nome = nome.strip()
    origem = origem.strip().upper()
    show_department_filter = user.role in {ROLE_ADMIN, ROLE_ANALYST}
    generated_ids_query = select(ProfileProposal.imported_result_profile_id).where(
        ProfileProposal.imported_result_profile_id.is_not(None)
    )
    generated_profile_ids = set(session.scalars(generated_ids_query).all())
    query = select(Perfil).options(selectinload(Perfil.departamento)).order_by(Perfil.nome)
    if user.role == ROLE_MANAGER:
        query = query.where(Perfil.id.in_(profile_ids_for_department(session, user.department_id)))
    elif departamento_id:
        query = query.where(Perfil.departamento_id == departamento_id)
    if nome:
        query = query.where(Perfil.nome.ilike(f'%{nome}%'))
    if origem == 'PROPOSTA':
        query = query.where(Perfil.id.in_(generated_profile_ids or {-1}))
    elif origem == 'ERP':
        query = query.where(Perfil.id.not_in(generated_profile_ids or {-1}))
    profiles = session.scalars(query).unique().all()
    departments = session.scalars(select(Departamento).order_by(Departamento.nome)).all() if show_department_filter else []
    return templates.TemplateResponse(
        request=request,
        name='portal_profiles.html',
        context={
            'user': user,
            'profiles': profiles,
            'departments': departments,
            'filter_name': nome,
            'filter_department_id': departamento_id,
            'filter_origin': origem,
            'show_department_filter': show_department_filter,
            'generated_profile_ids': generated_profile_ids,
        },
    )
'''
source = replace_route(source, "/portal/perfis'", "get", list_route)

detail_route = '''@router.get('/portal/perfis/{profile_id}', response_class=HTMLResponse)
def portal_profile_detail(
    request: Request,
    profile_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
):
    profile = session.scalar(
        select(Perfil)
        .options(
            selectinload(Perfil.departamento),
            selectinload(Perfil.acessos).selectinload(PerfilAcesso.acesso),
        )
        .where(Perfil.id == profile_id)
    )
    if not profile:
        raise HTTPException(404, 'Perfil nao encontrado')
    if user.role == ROLE_MANAGER and profile.id not in set(session.scalars(profile_ids_for_department(session, user.department_id)).all()):
        raise HTTPException(403, 'Perfil fora do departamento')
    proposal = session.scalar(
        select(ProfileProposal)
        .where(ProfileProposal.imported_result_profile_id == profile_id)
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
            'generated_proposal': proposal,
            'is_admin': user.role == ROLE_ADMIN,
        },
    )
'''
source = replace_route(source, "/portal/perfis/{profile_id}'", "get", detail_route)

# Remove rotas conflitantes e cria uma rota POST que usa /portal/perfis.
source = remove_route_if_exists(source, "/portal/perfis/{profile_id}/situacao", "post")
source = remove_route_if_exists(source, "/perfis/{profile_id}/situacao", "post")
status_route = '''

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
    generated = session.scalar(
        select(func.count()).select_from(ProfileProposal).where(
            ProfileProposal.imported_result_profile_id == profile_id
        )
    )
    if not generated:
        raise HTTPException(409, 'Somente perfis gerados em propostas podem ser inativados por esta acao')
    if situacao not in {'Ativo', 'Inativo'}:
        raise HTTPException(400, 'Situacao invalida')
    profile.situacao = situacao
    profile.ultima_atualizacao = datetime.now(timezone.utc)
    session.commit()
    return RedirectResponse(f'/portal/perfis/{profile.id}', status_code=303)
'''
source = source.rstrip() + status_route + "\n"

# Menu e links internos apontam para o mesmo fluxo.
base = BASE.read_text(encoding="utf-8-sig")
base = re.sub(r'href=["\']/perfis["\']', 'href="/portal/perfis"', base)

list_html = '''{% extends "base.html" %}
{% block title %}Perfis | Gestão de Acessos{% endblock %}
{% block content %}
<section class="hero compact">
  <p class="eyebrow">Perfis importados do ERP</p>
  <h1>Perfis</h1>
  <p>{% if user.department %}Perfis utilizados por funcionários de {{ user.department.nome }}.{% else %}Todos os perfis disponíveis para T.I.{% endif %}</p>
</section>
<form method="get" action="/portal/perfis" class="directory-filters">
  <label>Pesquisar por nome<input type="search" name="nome" value="{{ filter_name }}" placeholder="Digite o nome do perfil"></label>
  {% if show_department_filter %}<label>Departamento<select name="departamento_id"><option value="">Todos os departamentos</option>{% for d in departments %}<option value="{{ d.id }}" {% if filter_department_id == d.id %}selected{% endif %}>{{ d.nome }}</option>{% endfor %}</select></label>{% endif %}
  <label>Origem<select name="origem"><option value="">Todos os perfis</option><option value="PROPOSTA" {% if filter_origin == 'PROPOSTA' %}selected{% endif %}>Gerados em proposta</option><option value="ERP" {% if filter_origin == 'ERP' %}selected{% endif %}>Importados do ERP</option></select></label>
  <div class="filter-actions"><button type="submit">Filtrar</button><a href="/portal/perfis">Limpar</a></div>
</form>
<p class="filter-result">{{ profiles|length }} perfil(is) encontrado(s).</p>
<section class="people-grid">
{% for p in profiles %}
<a class="person-card" href="/portal/perfis/{{ p.id }}">
  <strong>{{ p.nome }}</strong>
  <span>{{ p.situacao }}</span>
  <small>{% if p.id in generated_profile_ids %}Gerado na proposta{% else %}Importado do ERP{% endif %}</small>
</a>
{% else %}<article class="panel">Nenhum perfil encontrado com os filtros informados.</article>{% endfor %}
</section>
{% endblock %}
'''

detail_html = '''{% extends "base.html" %}
{% block title %}{{ profile.nome }} | Gestão de Acessos{% endblock %}
{% block content %}
<a class="back" href="/portal/perfis">Voltar para perfis</a>
<section class="hero compact">
  <p class="eyebrow">Perfil</p>
  <h1>{{ profile.nome }}</h1>
  <p>{{ profile.situacao }} · {% if generated_proposal %}Gerado na proposta #{{ generated_proposal.id }}{% else %}Importado do ERP{% endif %}</p>
  {% if generated_proposal and is_admin %}
  <form method="post" action="/portal/perfis/{{ profile.id }}/situacao">
    <input type="hidden" name="situacao" value="{{ 'Inativo' if profile.situacao != 'Inativo' else 'Ativo' }}">
    <button type="submit">{{ 'Inativar perfil' if profile.situacao != 'Inativo' else 'Reativar perfil' }}</button>
  </form>
  {% endif %}
</section>
<section class="panel">
  <h2>Árvore de acessos</h2>
  {% set ns = namespace(path='', screen='', path_open=false, screen_open=false) %}
  {% for item in accesses %}{% set a = item.acesso %}
    {% if ns.path != a.caminho_completo %}
      {% if ns.screen_open %}</ul></details>{% set ns.screen_open = false %}{% endif %}
      {% if ns.path_open %}</div></details>{% endif %}
      <details open><summary><strong>{{ a.caminho_completo }}</strong></summary><div>
      {% set ns.path = a.caminho_completo %}{% set ns.screen = '' %}{% set ns.path_open = true %}
    {% endif %}
    {% if ns.screen != a.tela_final %}
      {% if ns.screen_open %}</ul></details>{% endif %}
      <details open><summary>{{ a.tela_final }}</summary><ul>
      {% set ns.screen = a.tela_final %}{% set ns.screen_open = true %}
    {% endif %}
    <li>{{ a.botao }} <small>({{ item.status }})</small></li>
  {% else %}<p>Este perfil não possui acessos cadastrados.</p>{% endfor %}
  {% if ns.screen_open %}</ul></details>{% endif %}
  {% if ns.path_open %}</div></details>{% endif %}
</section>
{% endblock %}
'''

for path in FILES:
    backup(path)

try:
    BACKEND.write_text(source, encoding="utf-8")
    BASE.write_text(base, encoding="utf-8")
    LIST.write_text(list_html, encoding="utf-8")
    DETAIL.write_text(detail_html, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("[OK] Menu Perfis aponta para /portal/perfis")
print("[OK] Padrao visual escolhido preservado em portal_profiles.html")
print("[OK] Filtro Gerados em proposta implementado no backend")
print("[OK] Inativar/Reativar visivel para ADMIN em perfil gerado por proposta")
print("[OK] Voltar retorna para a mesma tela")
print(f"\n[SUCESSO] Backup: {BACKUP}")
print("Nenhum CSS foi alterado. Reinicie o servidor e pressione Ctrl + F5.")
