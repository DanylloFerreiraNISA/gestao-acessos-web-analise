from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from app.database import engine
from app.access_control import SystemUser

with engine.begin() as connection:
    columns = {item["name"] for item in inspect(connection).get_columns("system_users")}
    if "username" not in columns:
        connection.execute(text("ALTER TABLE system_users ADD COLUMN username VARCHAR(120)"))
    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_system_users_username ON system_users (username)"))

with Session(engine) as session:
    users = session.scalars(select(SystemUser).order_by(SystemUser.id)).all()
    used = {item.username.lower() for item in users if item.username}
    for item in users:
        if item.username:
            continue
        base = "".join(char for char in item.email.split("@", 1)[0].lower() if char in "abcdefghijklmnopqrstuvwxyz0123456789._-") or f"usuario{item.id}"
        candidate = base
        number = 2
        while candidate in used:
            candidate = f"{base}.{number}"
            number += 1
        item.username = candidate
        used.add(candidate)
        print(f"{item.email} -> {candidate}")
    session.commit()
print("Migracao de username concluida.")
