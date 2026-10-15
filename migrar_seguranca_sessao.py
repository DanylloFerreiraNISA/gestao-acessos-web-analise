from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from app.database import engine
from app.access_control import LoginSession, SystemUser

with engine.begin() as connection:
    user_columns = {c['name'] for c in inspect(connection).get_columns('system_users')}
    if 'username' not in user_columns:
        connection.execute(text('ALTER TABLE system_users ADD COLUMN username VARCHAR(120)'))
    connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_system_users_username ON system_users (username)'))
    session_columns = {c['name'] for c in inspect(connection).get_columns('login_sessions')}
    if 'created_at' not in session_columns:
        connection.execute(text('ALTER TABLE login_sessions ADD COLUMN created_at TIMESTAMPTZ'))
    if 'last_activity_at' not in session_columns:
        connection.execute(text('ALTER TABLE login_sessions ADD COLUMN last_activity_at TIMESTAMPTZ'))
    connection.execute(text('UPDATE login_sessions SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP), last_activity_at = COALESCE(last_activity_at, CURRENT_TIMESTAMP)'))
    connection.execute(text('ALTER TABLE login_sessions ALTER COLUMN created_at SET NOT NULL'))
    connection.execute(text('ALTER TABLE login_sessions ALTER COLUMN last_activity_at SET NOT NULL'))
    connection.execute(text('CREATE INDEX IF NOT EXISTS ix_login_sessions_last_activity_at ON login_sessions (last_activity_at)'))

with Session(engine) as session:
    users = session.scalars(select(SystemUser).order_by(SystemUser.id)).all()
    used = {u.username.lower() for u in users if u.username}
    for user in users:
        if user.username:
            continue
        base = ''.join(c for c in user.email.split('@',1)[0].lower() if c in 'abcdefghijklmnopqrstuvwxyz0123456789._-') or f'usuario{user.id}'
        candidate, suffix = base, 2
        while candidate in used:
            candidate, suffix = f'{base}.{suffix}', suffix + 1
        user.username = candidate
        used.add(candidate)
        print(f'{user.email} -> {candidate}')
    session.commit()
print('Migracao concluida.')
