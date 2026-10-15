from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TARGET = ROOT / "app" / "templates" / "portal_profiles.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
SAFETY = ROOT / f"backup_antes_restaurar_layout_perfis_{STAMP}" / "app" / "templates" / "portal_profiles.html"

if not TARGET.exists():
    raise RuntimeError(f"Tela ativa nao encontrada: {TARGET}")

# Procura o layout anterior nos backups criados antes da atualizacao que desconfigurou a tela.
candidates: list[Path] = []
for folder in ROOT.iterdir():
    if not folder.is_dir():
        continue
    if not folder.name.startswith("backup_fluxo_perfil_aprovado_"):
        continue
    candidate = folder / "app" / "templates" / "portal_profiles.html"
    if candidate.exists():
        candidates.append(candidate)

if not candidates:
    raise RuntimeError(
        "Nenhum backup_fluxo_perfil_aprovado_* com portal_profiles.html foi encontrado. "
        "Nenhum arquivo foi alterado."
    )

# O primeiro backup dessa familia preserva melhor o layout anterior às tentativas subsequentes.
source = min(candidates, key=lambda p: p.parent.parent.parent.name)
original = source.read_text(encoding="utf-8-sig")

# Mantem o layout original e altera apenas textos/valores relacionados aos perfis criados.
updated = original
updated = updated.replace("Criado pelo sistema", "Gerado na proposta")
updated = updated.replace(">Sistema<", ">Gerado na proposta<")
updated = updated.replace("value=\"SISTEMA\"", "value=\"PROPOSTA\"")
updated = updated.replace("filter_origin == 'SISTEMA'", "filter_origin == 'PROPOSTA'")
updated = updated.replace("profile.id in system_profile_ids", "profile.id in generated_profile_ids")

# Se o template anterior ainda usava somente ERP sem a opcao criada, adiciona a opcao no select existente.
if "Gerado na proposta" not in updated and 'name="origem"' in updated:
    erp_option = "<option value=\"ERP\" {% if filter_origin == 'ERP' %}selected{% endif %}>Importado do ERP</option>"
    generated_option = erp_option + "\n      <option value=\"PROPOSTA\" {% if filter_origin == 'PROPOSTA' %}selected{% endif %}>Gerado na proposta</option>"
    updated = updated.replace(erp_option, generated_option, 1)

# Backup da tela atualmente desconfigurada, para reversao pontual se necessario.
SAFETY.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TARGET, SAFETY)
TARGET.write_text(updated, encoding="utf-8")

print("\n[SUCESSO] Layout anterior da tela de perfis restaurado.")
print(f"[ORIGEM] {source}")
print(f"[ALTERADO] {TARGET}")
print(f"[BACKUP DA TELA ATUAL] {SAFETY}")
print("[PRESERVADO] Nenhum CSS, backend, banco de dados ou outra tela foi alterado.")
print("[MANTIDO] Filtro e descricao 'Gerado na proposta'.")
print("\nReinicie o servidor e pressione Ctrl + F5.")
