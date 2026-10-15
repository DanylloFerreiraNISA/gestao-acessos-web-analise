from pathlib import Path
from datetime import datetime
import py_compile
import shutil

root = Path.cwd().resolve()
path = root / 'app' / 'access_control.py'
if not path.exists():
    raise SystemExit('ERRO: app/access_control.py não encontrado. Nada foi alterado.')

text = path.read_text(encoding='utf-8')
route = "@router.post('/portal/propostas/nova')"
start = text.find(route)
if start < 0:
    raise SystemExit('ERRO: rota POST /portal/propostas/nova não encontrada. Nada foi alterado.')
end = text.find('\n@router.', start + len(route))
if end < 0:
    end = len(text)
block = text[start:end]

if '# OPTIONAL_FORM_IDS_FIXED' in block:
    raise SystemExit('A correção dos campos opcionais já foi aplicada.')

old_profile = "source_profile_id: Annotated[int | None, Form()] = None"
old_employee = "source_employee_id: Annotated[int | None, Form()] = None"
if old_profile not in block or old_employee not in block:
    raise SystemExit('ERRO: assinatura da rota não corresponde à versão esperada. Nada foi alterado.')

backup = root / f"backup_criacao_proposta_{datetime.now():%Y%m%d_%H%M%S}"
target = backup / 'app' / 'access_control.py'
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(path, target)

block = block.replace(
    old_profile,
    "source_profile_id: Annotated[str, Form()] = ''",
    1,
).replace(
    old_employee,
    "source_employee_id: Annotated[str, Form()] = ''",
    1,
)

signature_end = block.find('):')
if signature_end < 0:
    shutil.copy2(target, path)
    raise SystemExit('ERRO: final da assinatura não encontrado; arquivo restaurado.')

normalization = """
    # OPTIONAL_FORM_IDS_FIXED: selects HTML enviam string vazia quando nenhuma base é escolhida.
    try:
        source_profile_id = int(source_profile_id) if source_profile_id.strip() else None
        source_employee_id = int(source_employee_id) if source_employee_id.strip() else None
    except ValueError:
        raise HTTPException(status_code=400, detail='Perfil ou funcionário base inválido')
"""
block = block[:signature_end + 2] + normalization + block[signature_end + 2:]
updated = text[:start] + block + text[end:]
path.write_text(updated, encoding='utf-8', newline='\n')

try:
    py_compile.compile(str(path), doraise=True)
except Exception:
    shutil.copy2(target, path)
    raise

print('Correção aplicada com sucesso.')
print('Campos vazios de perfil e funcionário agora são convertidos para None.')
print('Backup:', backup)
