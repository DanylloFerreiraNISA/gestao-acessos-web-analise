from __future__ import annotations

import py_compile
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
BACKUP = ROOT / f"backup_restaurar_arvore_classica_{STAMP}"

for path in (BACKEND, LIST, DETAIL):
    if not path.exists():
        raise RuntimeError(f"Arquivo necessario nao encontrado: {path}")


def backup(path: Path) -> None:
    target = BACKUP / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore() -> None:
    if not BACKUP.exists():
        return
    for source in BACKUP.rglob("*"):
        if source.is_file():
            target = ROOT / source.relative_to(BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


print("\nRESTAURACAO DA ARVORE CLASSICA DO PERFIL")
print(f"Projeto: {ROOT}")
print("A lista continuara no padrao solicitado e o detalhe voltara a usar a arvore classica.\n")

backend = BACKEND.read_text(encoding="utf-8-sig")
list_html = LIST.read_text(encoding="utf-8-sig")

# A lista visual escolhida continua sendo portal_profiles.html, mas o cartão abre
# a rota clássica /perfis/{id}, que prepara os dados usados por _classic_access.html.
list_html = list_html.replace(
    'href="/portal/perfis/{{ p.id }}"',
    'href="/perfis/{{ p.id }}"',
)

# Template clássico limpo. A correção anterior havia colocado formulário e script
# dentro do bloco title, o que deformava a página e a árvore.
detail_html = '''{% extends "base.html" %}
{% block title %}{{ perfil.nome }}{% endblock %}
{% block content %}
<a class="back" href="/portal/perfis">Voltar para perfis</a>
<section class="hero compact">
  <p class="eyebrow">Perfil</p>
  <h1>{{ perfil.nome }}</h1>
  <p>{{ usuarios|length }} usuarios vinculados</p>
  <p id="profile-origin-label"></p>
  <section id="proposal-profile-actions" hidden>
    <form method="post" action="/perfis/{{ perfil.id }}/situacao">
      <input type="hidden" name="situacao" value="{{ 'Inativo' if perfil.situacao != 'Inativo' else 'Ativo' }}">
      <button type="submit">{{ 'Inativar perfil' if perfil.situacao != 'Inativo' else 'Reativar perfil' }}</button>
    </form>
  </section>
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
    const label = document.getElementById('profile-origin-label');
    label.textContent = data.generated ? 'Gerado na proposta' : 'Importado do ERP';
    if (data.generated && data.can_manage) {
      document.getElementById('proposal-profile-actions').hidden = false;
    }
  });
</script>
{% endblock %}
'''

# Confirma que os endpoints necessários ainda existem. Não recria nem duplica rotas.
required = [
    "@router.get('/api/perfis/{profile_id}/origem-proposta')",
    "@router.post('/perfis/{profile_id}/situacao')",
]
missing = [item for item in required if item not in backend]
if missing:
    raise RuntimeError(
        "As rotas necessarias para origem/inativacao nao existem no backend atual: "
        + ", ".join(missing)
        + ". Nenhum arquivo foi alterado."
    )

for path in (BACKEND, LIST, DETAIL):
    backup(path)

try:
    LIST.write_text(list_html, encoding="utf-8")
    DETAIL.write_text(detail_html, encoding="utf-8")
    py_compile.compile(str(BACKEND), doraise=True)
except Exception:
    restore()
    raise

print("[OK] Arvore classica restaurada por _classic_access.html")
print("[OK] Cartoes da tela escolhida abrem /perfis/{id}")
print("[OK] Voltar retorna para /portal/perfis")
print("[OK] Inativar/Reativar permanece disponivel para perfil gerado por proposta e ADMIN")
print("[OK] Nenhum CSS ou backend foi modificado")
print(f"[BACKUP] {BACKUP}")
print("\nReinicie o servidor e pressione Ctrl + F5.")
