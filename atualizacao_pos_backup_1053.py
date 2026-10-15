from __future__ import annotations

from datetime import datetime
from pathlib import Path
import py_compile
import shutil
import sys

ROOT = Path.cwd()
APP = ROOT / "app"
ACCESS = APP / "access_control.py"
TEMPLATE = APP / "templates" / "accounts.html"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_antes_atualizacao_{STAMP}"


def fail(message: str) -> None:
    raise SystemExit(f"ERRO: {message}")


def backup_file(path: Path) -> None:
    relative = path.relative_to(ROOT)
    target = BACKUP / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_backup() -> None:
    if not BACKUP.exists():
        return
    for source in BACKUP.rglob("*"):
        if source.is_file():
            target = ROOT / source.relative_to(BACKUP)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def update_accounts_template() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    marker = "{% block content %}"
    fallback = (
        "{% set account_list = accounts if accounts is defined else "
        "(users if users is defined else "
        "(system_users if system_users is defined else [])) %}"
    )
    if "{% set account_list =" not in html:
        if marker not in html:
            fail("Bloco content nao encontrado em app/templates/accounts.html")
        html = html.replace(marker, marker + "\n" + fallback, 1)
    html = html.replace(
        "{% for account in accounts %}",
        "{% for account in account_list %}",
    )
    TEMPLATE.write_text(html, encoding="utf-8", newline="\n")


def update_accounts_route() -> None:
    text = ACCESS.read_text(encoding="utf-8")
    route_marker = "@router.get('/admin/contas'"
    start = text.find(route_marker)
    if start < 0:
        fail("Rota GET /admin/contas nao encontrada em app/access_control.py")

    next_route = text.find("\n@router.", start + 1)
    if next_route < 0:
        next_route = len(text)
    block = text[start:next_route]
    func_at = block.find("\ndef ")
    if func_at < 0:
        fail("Funcao da rota /admin/contas nao encontrada")
    func_line_end = block.find("\n", func_at + 1)
    signature = block[func_at + 1:func_line_end]
    func_name = signature.split("def ", 1)[1].split("(", 1)[0].strip()

    new_block = f'''@router.get('/admin/contas', response_class=HTMLResponse)
def {func_name}(
    request: Request,
    session: Db,
    user: Annotated[SystemUser, Depends(require_admin)],
):
    accounts = session.scalars(
        select(SystemUser)
        .options(selectinload(SystemUser.department))
        .order_by(SystemUser.name, SystemUser.email)
    ).all()
    departments = session.scalars(
        select(Departamento).order_by(Departamento.nome)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name='accounts.html',
        context={{
            'current_user': user,
            'user': user,
            'accounts': accounts,
            'users': accounts,
            'system_users': accounts,
            'departments': departments,
            'error': None,
        }},
    )
'''
    ACCESS.write_text(text[:start] + new_block + text[next_route:], encoding="utf-8", newline="\n")


def validate() -> None:
    py_compile.compile(str(ACCESS), doraise=True)
    html = TEMPLATE.read_text(encoding="utf-8")
    if "account_list" not in html:
        fail("Validacao do template falhou")


def main() -> None:
    print("Atualizacao consolidada posterior ao backup das 10:53")
    print(f"Pasta do sistema: {ROOT}")
    for path in (ACCESS, TEMPLATE):
        if not path.exists():
            fail(f"Arquivo esperado nao encontrado: {path}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ACCESS)
    backup_file(TEMPLATE)

    try:
        update_accounts_template()
        update_accounts_route()
        validate()
    except Exception as exc:
        restore_backup()
        fail(f"Alteracao desfeita automaticamente: {exc}")

    print("OK: atualizacao aplicada e validada.")
    print(f"Backup de seguranca: {BACKUP}")
    print("- Lista de contas volta a consultar os usuarios existentes")
    print("- Templates antigos continuam aceitando accounts, users ou system_users")
    print("- Nenhuma conta e recriada ou excluida")
    print("AVISO: a tela demonstrativa de propostas nao foi aplicada, pois ela substitui a estrutura do sistema.")


if __name__ == "__main__":
    main()
