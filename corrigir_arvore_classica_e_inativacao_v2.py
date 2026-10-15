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
LIST = APP / "templates" / "portal_profiles.html"
DETAIL = APP / "templates" / "perfil.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_arvore_classica_inativacao_{STAMP}"
MARK = "# API_ORIGEM_PERFIL_PROPOSTA_CLASSICA_V2"

for path in (BACKEND, LIST, DETAIL):
    if not path.exists():
        raise RuntimeError(f"Arquivo necessario nao encontrado: {path}")


def backup(path: Path) -> None:
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def restore() -> None:
    if not BACKUP.exists():
        return
    for source in BACKUP.rglob("*"):
        if source.is_file():
            target = ROOT / source.relative_to(BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


print("\nCORRECAO DA ARVORE CLASSICA E INATIVACAO - V2")
print(f"Projeto: {ROOT}")
print("A arvore voltara a usar _classic_access.html. Nenhum CSS sera alterado.\n")

backend = BACKEND.read_text(encoding="utf-8-sig")
list_html = LIST.read_text(encoding="utf-8-sig")

# A rota POST real, confirmada pelo diagnostico, e /portal/perfis/{id}/situacao.
status_route = "@router.post('/portal/perfis/{profile_id}/situacao')"
if status_route not in backend:
    raise RuntimeError(
        "A rota POST /portal/perfis/{profile_id}/situacao nao foi encontrada no backend atual. "
        "Nenhum arquivo foi alterado."
    )

# Recria somente a API de consulta de origem, caso a correcao anterior a tenha removido.
api_route = "@router.get('/api/perfis/{profile_id}/origem-proposta')"
if api_route not in backend:
    api_code = f'''\n\n{MARK}\n@router.get('/api/perfis/{{profile_id}}/origem-proposta')
def classic_profile_proposal_origin(
    profile_id: int,
    session: Db,
    user: Annotated[SystemUser, Depends(require_user)],
):
    generated = session.scalar(
        select(func.count()).select_from(ProfileProposal).where(
            ProfileProposal.imported_result_profile_id == profile_id
        )
    )
    return {{'generated': bool(generated), 'can_manage': user.role == ROLE_ADMIN}}
'''
    backend = backend.rstrip() + api_code + "\n"

# Preserva a listagem no padrão escolhido, mas abre o detalhe clássico /perfis/{id}.
list_html = list_html.replace(
    'href="/portal/perfis/{{ p.id }}"',
    'href="/perfis/{{ p.id }}"',
)

# Restaura o template clássico sem inserir conteúdo dentro do bloco title.
detail_html = '''{% extends "base.html" %}
{% block title %}{{ perfil.nome }}{% endblock %}
{% block content %}
<a class="back" href="/portal/perfis">Voltar para perfis</a>
<section class="hero compact">
  <p class="eyebrow">Perfil</p>
  <h1>{{ perfil.nome }}</h1>
  <p>{{ usuarios|length }} usuarios vinculados</p>
  <p id="profile-origin-label"></p>
  <div id="proposal-profile-actions" hidden>
    <form method="post" action="/portal/perfis/{{ perfil.id }}/situacao">
      <input type="hidden" name="situacao" value="{{ 'Inativo' if perfil.situacao != 'Inativo' else 'Ativo' }}">
      <button type="submit">{{ 'Inativar perfil' if perfil.situacao != 'Inativo' else 'Reativar perfil' }}</button>
    </form>
  </div>
</section>

<script type="application/json" id="classic-profile">{{ acessos|tojson }}</script>
{% set source_id='classic-profile' %}
{% set compare=false %}
{% include '_classic_access.html' %}

<script>
fetch('/api/perfis/{{ perfil.id }}/origem-proposta')
  .then(response => response.ok ? response.json() : null)
  .then(data => {
    if (!data) return;
    document.getElementById('profile-origin-label').textContent =
      data.generated ? 'Gerado na proposta' : 'Importado do ERP';
    if (data.generated && data.can_manage) {
      document.getElementById('proposal-profile-actions').hidden = false;
    }
  });
</script>
{% endblock %}
'''

for path in (BACKEND, LIST, DETAIL):
    backup(path)

try:
    BACKEND.write_text(backend, encoding="utf-8")
    LIST.write_text(list_html, encoding="utf-8")
    DETAIL.write_text(detail_html, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("[OK] Arvore classica restaurada com _classic_access.html")
print("[OK] Perfil abre pela rota classica /perfis/{id}")
print("[OK] Voltar retorna para a listagem escolhida /portal/perfis")
print("[OK] Botao Inativar/Reativar usa a rota existente /portal/perfis/{id}/situacao")
print("[OK] Botao aparece somente para ADMIN e perfil gerado em proposta")
print("[OK] Nenhum CSS foi alterado")
print(f"[BACKUP] {BACKUP}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
