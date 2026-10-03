from pathlib import Path
import py_compile

ROOT = Path.cwd()
APP = ROOT / 'app'
TEMPLATES = APP / 'templates'
STATIC = APP / 'static'
for folder in (APP, TEMPLATES, STATIC):
    folder.mkdir(parents=True, exist_ok=True)
(APP / '__init__.py').touch(exist_ok=True)

MAIN = '''from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, get_database_session
from app.models import Acesso, Funcionario, FuncionarioPerfil, Perfil, PerfilAcesso

app = FastAPI(title=settings.app_name, version="0.2.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
DatabaseSession = Annotated[Session, Depends(get_database_session)]


@app.get("/health")
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"aplicacao": "online", "banco": "online"}


@app.get("/api/resumo")
def api_resumo(session: DatabaseSession):
    return {
        "funcionarios": session.scalar(select(func.count()).select_from(Funcionario)) or 0,
        "perfis": session.scalar(select(func.count()).select_from(Perfil)) or 0,
        "acessos": session.scalar(select(func.count()).select_from(Acesso)) or 0,
        "vinculos": session.scalar(select(func.count()).select_from(FuncionarioPerfil)) or 0,
        "permissoes": session.scalar(select(func.count()).select_from(PerfilAcesso)) or 0,
    }


@app.get("/api/funcionarios")
def api_funcionarios(
    session: DatabaseSession,
    busca: str = "",
    limite: int = Query(default=100, ge=1, le=500),
):
    stmt = select(Funcionario).order_by(Funcionario.nome).limit(limite)
    if busca.strip():
        termo = f"%{busca.strip()}%"
        stmt = stmt.where(or_(Funcionario.nome.ilike(termo), Funcionario.login.ilike(termo)))
    itens = session.scalars(stmt).all()
    return [
        {
            "id": item.id,
            "login": item.login,
            "nome": item.nome,
            "ativo": item.ativo,
            "departamento": item.departamento.nome if item.departamento else None,
        }
        for item in itens
    ]


@app.get("/api/perfis")
def api_perfis(
    session: DatabaseSession,
    busca: str = "",
    limite: int = Query(default=100, ge=1, le=500),
):
    stmt = select(Perfil).order_by(Perfil.nome).limit(limite)
    if busca.strip():
        stmt = stmt.where(Perfil.nome.ilike(f"%{busca.strip()}%"))
    itens = session.scalars(stmt).all()
    return [
        {
            "id": item.id,
            "nome": item.nome,
            "situacao": item.situacao,
            "ultima_atualizacao": item.ultima_atualizacao,
        }
        for item in itens
    ]


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: DatabaseSession):
    resumo = {
        "funcionarios": session.scalar(select(func.count()).select_from(Funcionario)) or 0,
        "perfis": session.scalar(select(func.count()).select_from(Perfil)) or 0,
        "acessos": session.scalar(select(func.count()).select_from(Acesso)) or 0,
        "vinculos": session.scalar(select(func.count()).select_from(FuncionarioPerfil)) or 0,
        "permissoes": session.scalar(select(func.count()).select_from(PerfilAcesso)) or 0,
    }
    perfis = session.scalars(select(Perfil).order_by(Perfil.nome).limit(50)).all()
    funcionarios = session.scalars(select(Funcionario).order_by(Funcionario.nome).limit(50)).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"resumo": resumo, "perfis": perfis, "funcionarios": funcionarios},
    )
'''

HTML = '''<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Gestao de Acessos</title>
  <link rel="stylesheet" href="{{ url_for('static', path='/styles.css') }}">
</head>
<body>
  <header>
    <div>
      <p class="eyebrow">Grupo Nisa</p>
      <h1>Gestao de Acessos</h1>
      <p>Dados carregados diretamente do PostgreSQL.</p>
    </div>
    <a class="button" href="/docs">Documentacao da API</a>
  </header>

  <main>
    <section class="cards">
      <article><span>Funcionarios</span><strong>{{ resumo.funcionarios }}</strong></article>
      <article><span>Perfis</span><strong>{{ resumo.perfis }}</strong></article>
      <article><span>Acessos</span><strong>{{ resumo.acessos }}</strong></article>
      <article><span>Vinculos</span><strong>{{ resumo.vinculos }}</strong></article>
      <article><span>Permissoes</span><strong>{{ resumo.permissoes }}</strong></article>
    </section>

    <section class="grid">
      <article class="panel">
        <div class="panel-title"><h2>Perfis</h2><a href="/api/perfis">Ver JSON</a></div>
        <input type="search" placeholder="Filtrar perfis" data-filter="profiles-table">
        <div class="table-wrap">
          <table id="profiles-table">
            <thead><tr><th>Perfil</th><th>Situacao</th></tr></thead>
            <tbody>
              {% for perfil in perfis %}
              <tr><td>{{ perfil.nome }}</td><td><span class="status">{{ perfil.situacao }}</span></td></tr>
              {% else %}
              <tr><td colspan="2">Nenhum perfil importado.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-title"><h2>Funcionarios</h2><a href="/api/funcionarios">Ver JSON</a></div>
        <input type="search" placeholder="Filtrar funcionario ou login" data-filter="employees-table">
        <div class="table-wrap">
          <table id="employees-table">
            <thead><tr><th>Nome</th><th>Login</th><th>Departamento</th></tr></thead>
            <tbody>
              {% for funcionario in funcionarios %}
              <tr>
                <td>{{ funcionario.nome }}</td>
                <td>{{ funcionario.login }}</td>
                <td>{{ funcionario.departamento.nome if funcionario.departamento else 'Nao definido' }}</td>
              </tr>
              {% else %}
              <tr><td colspan="3">Nenhum funcionario importado.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  </main>
  <script src="{{ url_for('static', path='/app.js') }}"></script>
</body>
</html>
'''

CSS = '''*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#172033;font-family:Segoe UI,Arial,sans-serif}header{display:flex;justify-content:space-between;align-items:center;gap:24px;padding:30px 5vw;background:#17365d;color:#fff}h1,h2,p{margin-top:0}.eyebrow{margin-bottom:6px;text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:#b9d8f5}.button{color:#17365d;background:#fff;text-decoration:none;padding:10px 14px;border-radius:8px;font-weight:700}main{width:min(1500px,94vw);margin:24px auto}.cards{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:14px}.cards article,.panel{background:#fff;border:1px solid #d8e2ec;border-radius:12px;box-shadow:0 4px 16px rgba(20,48,78,.06)}.cards article{padding:18px}.cards span{display:block;color:#667085;font-size:13px}.cards strong{display:block;margin-top:6px;font-size:30px;color:#17365d}.grid{display:grid;grid-template-columns:1fr 1.3fr;gap:18px;margin-top:20px}.panel{padding:18px;min-width:0}.panel-title{display:flex;align-items:center;justify-content:space-between}.panel-title a{color:#1f4e78}input{width:100%;padding:10px 12px;border:1px solid #aebdca;border-radius:8px;margin:4px 0 14px}.table-wrap{overflow:auto;max-height:60vh}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #e7edf3;font-size:14px}th{position:sticky;top:0;background:#eef4fa;color:#17365d}.status{display:inline-block;padding:3px 8px;border-radius:999px;background:#e6f3ff;color:#174d7a}@media(max-width:950px){header{align-items:flex-start;flex-direction:column}.cards{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}'''

JS = '''document.querySelectorAll('[data-filter]').forEach(input=>{input.addEventListener('input',()=>{const q=input.value.toLocaleLowerCase('pt-BR');document.querySelectorAll(`#${input.dataset.filter} tbody tr`).forEach(row=>{row.style.display=row.innerText.toLocaleLowerCase('pt-BR').includes(q)?'':'none'})})});'''

(APP / 'main.py').write_text(MAIN, encoding='utf-8', newline='\n')
(TEMPLATES / 'dashboard.html').write_text(HTML, encoding='utf-8', newline='\n')
(STATIC / 'styles.css').write_text(CSS, encoding='utf-8', newline='\n')
(STATIC / 'app.js').write_text(JS, encoding='utf-8', newline='\n')
py_compile.compile(str(APP / 'main.py'), doraise=True)
print('Primeira API e dashboard configurados.')
print(r'Execute: uvicorn app.main:app --reload')
