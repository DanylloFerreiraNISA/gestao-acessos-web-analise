from getpass import getpass
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import engine
from app.access_control import ROLE_ADMIN, SystemUser, create_tables, hash_password

create_tables()
email = input("E-mail do admin T.I.: ").strip().lower()
name = input("Nome: ").strip()
password = getpass("Senha inicial: ")
if len(password) < 10:
    raise SystemExit("Use uma senha com pelo menos 10 caracteres.")
with Session(engine) as session:
    if session.scalar(select(SystemUser).where(SystemUser.email == email)):
        raise SystemExit("Conta ja existe.")
    session.add(SystemUser(name=name, email=email, password_hash=hash_password(password), role=ROLE_ADMIN, active=True))
    session.commit()
print("Admin T.I. criado.")
