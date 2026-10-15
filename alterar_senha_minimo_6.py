from pathlib import Path
from datetime import datetime
import py_compile
import shutil

root = Path.cwd().resolve()
path = root / 'app' / 'access_control.py'
if not path.is_file():
    raise SystemExit('ERRO: app/access_control.py nao encontrado. Nada foi alterado.')

text = path.read_text(encoding='utf-8')
backup = root / f"backup_senha_minimo_6_{datetime.now():%Y%m%d_%H%M%S}"
target = backup / 'app' / 'access_control.py'
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(path, target)

old_edit = "elif new_password and len(new_password) < 10:\n        error = 'A nova senha precisa ter pelo menos 10 caracteres.'"
new_edit = "elif new_password and len(new_password) < 6:\n        error = 'A nova senha precisa ter pelo menos 6 caracteres.'"

if old_edit not in text and new_edit not in text:
    raise SystemExit('ERRO: validacao de edicao de senha nao encontrada. Nada foi alterado.')
text = text.replace(old_edit, new_edit, 1)

create_signature = "def account_create(session: Db, user: Annotated[SystemUser, Depends(require_admin)], name: Annotated[str, Form()], username: Annotated[str, Form()], email: Annotated[str, Form()], password: Annotated[str, Form()], role: Annotated[str, Form()], department_id: Annotated[int | None, Form()] = None):"
create_validation = "\n    if len(password) < 6: raise HTTPException(400, 'A senha precisa ter pelo menos 6 caracteres')"

if create_signature not in text:
    raise SystemExit('ERRO: rota de criacao de conta nao encontrada. Nada foi alterado.')
if "if len(password) < 6: raise HTTPException(400, 'A senha precisa ter pelo menos 6 caracteres')" not in text:
    text = text.replace(create_signature, create_signature + create_validation, 1)

path.write_text(text, encoding='utf-8', newline='\n')
try:
    py_compile.compile(str(path), doraise=True)
except Exception:
    shutil.copy2(target, path)
    raise

print('Validacao de senha atualizada com sucesso.')
print('- Criacao de conta: minimo de 6 caracteres')
print('- Alteracao de senha: minimo de 6 caracteres')
print('Backup:', backup)
