from pathlib import Path
import py_compile

ROOT = Path.cwd()
APP = ROOT / "app"
TEMPLATES = APP / "templates"
STATIC = APP / "static"
for folder in (APP, TEMPLATES, STATIC):
    folder.mkdir(parents=True, exist_ok=True)

MAIN = '''from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import engine, get_database_session
from app.models import Acesso, Departamento, Funcionario, FuncionarioPerfil, Perfil, PerfilAcesso

app = FastAPI(title=settings.app_name, version="0.3.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
DatabaseSession = Annotated[Session, Depends(get_database_session)]


def resumo(session: Session):
    return {
        "funcionarios": session.scalar(select(func.count()).select_from(Funcionario)) or 0,
        "perfis": session.scalar(select(func.count()).select_from(Perfil)) or 0,
        "acessos": session.scalar(select(func.count()).select_from(Acesso)) or 0,
        "vinculos": session.scalar(select(func.count()).select_from(FuncionarioPerfil)) or 0,
        "permissoes": session.scalar(select(func.count()).select_from(PerfilAcesso)) or 0,
    }


def consolidado_funcionario(session: Session, funcionario_id: int):
    rows = session.execute(
        select(
            Acesso.id,
            Acesso.caminho_completo,
            Acesso.tela_final,
            Acesso.botao,
            PerfilAcesso.status,
            Perfil.nome.label("perfil_nome"),
        )
        .join(PerfilAcesso, PerfilAcesso.acesso_id == Acesso.id)
        .join(Perfil, Perfil.id == PerfilAcesso.perfil_id)
        .join(FuncionarioPerfil, FuncionarioPerfil.perfil_id == Perfil.id)
        .where(FuncionarioPerfil.funcionario_id == funcionario_id)
        .order_by(Acesso.caminho_completo, Acesso.tela_final, Acesso.botao)
    ).all()

    agrupado = {}
    for row in rows:
        item = agrupado.setdefault(
            row.id,
            {
                "id": row.id,
                "caminho": row.caminho_completo,
                "tela": row.tela_final,
                "botao": row.botao,
                "status": "Nao identificado",
                "perfis": [],
            },
        )
        item["perfis"].append({"nome": row.perfil_nome, "status": row.status})
        if str(row.status).casefold() == "permitido":
            item["status"] = "Permitido"
        elif item["status"] != "Permitido" and str(row.status).casefold() == "negado":
            item["status"] = "Negado"

    prioridade = {"Permitido": 0, "Nao identificado": 1, "Negado": 2}
    return sorted(
        agrupado.values(),
        key=lambda item: (
            prioridade.get(item["status"], 1),
            item["caminho"].casefold(),
            item["tela"].casefold(),
            item["botao"].casefold(),
        ),
    )


@app.get("/health")
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"aplicacao": "online", "banco": "online"}


@app.get("/api/resumo")
def api_resumo(session: DatabaseSession):
    return resumo(session)


@app.get("/api/funcionarios")
def api_funcionarios(
    session: DatabaseSession,
    busca: str = "",
    departamento: str = "",
    limite: int = Query(default=100, ge=1, le=500),
):
    stmt = (
        select(Funcionario)
        .options(selectinload(Funcionario.departamento))
        .order_by(Funcionario.nome)
        .limit(limite)
    )
    if busca.strip():
        termo = f"%{busca.strip()}%"
        stmt = stmt.where(or_(Funcionario.nome.ilike(termo), Funcionario.login.ilike(termo)))
    if departamento.strip():
        stmt = stmt.join(Departamento).where(Departamento.nome == departamento.strip())
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
def api_perfis(session: DatabaseSession, busca: str = ""):
    stmt = select(Perfil).order_by(Perfil.nome)
    if busca.strip():
        stmt = stmt.where(Perfil.nome.ilike(f"%{busca.strip()}%"))
    return [
        {"id": item.id, "nome": item.nome, "situacao": item.situacao}
        for item in session.scalars(stmt).all()
    ]


@app.get("/api/funcionarios/{funcionario_id}/consolidado")
def api_consolidado(funcionario_id: int, session: DatabaseSession):
    funcionario = session.get(Funcionario, funcionario_id)
    if funcionario is None:
        raise HTTPException(status_code=404, detail="Funcionario nao encontrado")
    return consolidado_funcionario(session, funcionario_id)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: DatabaseSession):
    funcionarios = session.scalars(
        select(Funcionario)
        .options(selectinload(Funcionario.departamento))
        .order_by(Funcionario.nome)
        .limit(50)
    ).all()
    perfis = session.scalars(select(Perfil).order_by(Perfil.nome).limit(50)).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"resumo": resumo(session), "perfis": perfis, "funcionarios": funcionarios},
    )


@app.get("/estrutura", response_class=HTMLResponse)
def estrutura_atual(
    request: Request,
    session: DatabaseSession,
    busca: str = "",
    departamento: str = "",
):
    stmt = (
        select(Funcionario)
        .options(selectinload(Funcionario.departamento))
        .order_by(Funcionario.nome)
    )
    if busca.strip():
        termo = f"%{busca.strip()}%"
        stmt = stmt.where(or_(Funcionario.nome.ilike(termo), Funcionario.login.ilike(termo)))
    if departamento.strip():
        stmt = stmt.join(Departamento).where(Departamento.nome == departamento.strip())
    funcionarios = session.scalars(stmt).all()
    departamentos = session.scalars(select(Departamento).order_by(Departamento.nome)).all()
    return templates.TemplateResponse(
        request=request,
        name="estrutura.html",
        context={
            "funcionarios": funcionarios,
            "departamentos": departamentos,
            "busca": busca,
            "departamento_selecionado": departamento,
        },
    )


@app.get("/funcionarios/{funcionario_id}", response_class=HTMLResponse)
def funcionario_detalhe(request: Request, funcionario_id: int, session: DatabaseSession):
    funcionario = session.scalar(
        select(Funcionario)
        .options(
            selectinload(Funcionario.departamento),
            selectinload(Funcionario.perfis).selectinload(FuncionarioPerfil.perfil),
        )
        .where(Funcionario.id == funcionario_id)
    )
    if funcionario is None:
        raise HTTPException(status_code=404, detail="Funcionario nao encontrado")
    acessos = consolidado_funcionario(session, funcionario_id)
    return templates.TemplateResponse(
        request=request,
        name="funcionario.html",
        context={"funcionario": funcionario, "acessos": acessos},
    )
'''

BASE = '''<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}Gestao de Acessos{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', path='/styles.css') }}">
</head>
<body>
<header class="topbar">
  <a class="brand" href="/">Gestao de Acessos</a>
  <nav><a href="/">Resumo</a><a href="/estrutura">Estrutura atual</a><a href="/docs">API</a></nav>
</header>
<main class="container">{% block content %}{% endblock %}</main>
<script src="{{ url_for('static', path='/app.js') }}"></script>
</body>
</html>
'''

DASHBOARD = '''{% extends "base.html" %}
{% block title %}Resumo | Gestao de Acessos{% endblock %}
{% block content %}
<section class="hero"><p class="eyebrow">PostgreSQL conectado</p><h1>Resumo do ambiente</h1><p>Dados atuais de usuarios, perfis e permissoes.</p></section>
<section class="cards">
  {% for nome, total in resumo.items() %}<article><span>{{ nome|replace('_',' ')|title }}</span><strong>{{ total }}</strong></article>{% endfor %}
</section>
<section class="panel action-panel"><h2>Estrutura atual</h2><p>Consulte funcionarios, perfis vinculados e o consolidado de acessos.</p><a class="button" href="/estrutura">Abrir estrutura atual</a></section>
{% endblock %}
'''

ESTRUTURA = '''{% extends "base.html" %}
{% block title %}Estrutura atual{% endblock %}
{% block content %}
<section class="hero"><p class="eyebrow">Consulta</p><h1>Estrutura atual</h1><p>Funcionarios ativos e seus dados organizacionais.</p></section>
<form class="filters" method="get">
  <input name="busca" value="{{ busca }}" placeholder="Pesquisar nome ou login">
  <select name="departamento">
    <option value="">Todos os departamentos</option>
    {% for item in departamentos %}<option value="{{ item.nome }}" {% if item.nome == departamento_selecionado %}selected{% endif %}>{{ item.nome }}</option>{% endfor %}
  </select>
  <button type="submit">Filtrar</button><a href="/estrutura" class="secondary">Limpar</a>
</form>
<section class="panel">
  <div class="panel-title"><h2>Funcionarios</h2><span>{{ funcionarios|length }} encontrados</span></div>
  <div class="people-grid">
    {% for item in funcionarios %}
    <a class="person-card" href="/funcionarios/{{ item.id }}">
      <strong>{{ item.nome }}</strong><span>{{ item.login }}</span><small>{{ item.departamento.nome if item.departamento else 'Departamento nao definido' }}</small>
    </a>
    {% else %}<p>Nenhum funcionario encontrado.</p>{% endfor %}
  </div>
</section>
{% endblock %}
'''

FUNCIONARIO = '''{% extends "base.html" %}
{% block title %}{{ funcionario.nome }}{% endblock %}
{% block content %}
<a class="back" href="/estrutura">Voltar para estrutura atual</a>
<section class="hero compact"><p class="eyebrow">Funcionario</p><h1>{{ funcionario.nome }}</h1><p>{{ funcionario.login }} | {{ funcionario.departamento.nome if funcionario.departamento else 'Departamento nao definido' }}</p></section>
<section class="profile-layout">
  <article class="panel"><h2>Perfis vinculados</h2><div class="chips">{% for vinculo in funcionario.perfis %}<span>{{ vinculo.perfil.nome }}</span>{% else %}<p>Nenhum perfil vinculado.</p>{% endfor %}</div></article>
  <article class="panel"><h2>Consolidado</h2><div class="stats"><span><b>{{ acessos|selectattr('status','equalto','Permitido')|list|length }}</b> Permitidos</span><span><b>{{ acessos|selectattr('status','equalto','Negado')|list|length }}</b> Negados</span><span><b>{{ acessos|length }}</b> Total</span></div></article>
</section>
<section class="panel">
  <div class="panel-title"><h2>Acessos consolidados</h2><input type="search" placeholder="Pesquisar acesso" data-filter="access-table"></div>
  <div class="table-wrap"><table id="access-table"><thead><tr><th>Botao</th><th>Tela</th><th>Caminho</th><th>Status</th></tr></thead><tbody>
  {% for acesso in acessos %}<tr><td>{{ acesso.botao }}</td><td>{{ acesso.tela }}</td><td>{{ acesso.caminho }}</td><td><span class="status {{ acesso.status|lower|replace(' ','-') }}">{{ acesso.status }}</span></td></tr>{% else %}<tr><td colspan="4">Nenhum acesso disponível.</td></tr>{% endfor %}
  </tbody></table></div>
</section>
{% endblock %}
'''

CSS = '''*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#172033;font-family:Segoe UI,Arial,sans-serif}.topbar{display:flex;justify-content:space-between;align-items:center;padding:15px 4vw;background:#17365d;color:white}.brand,.topbar a{color:white;text-decoration:none}.brand{font-size:20px;font-weight:800}.topbar nav{display:flex;gap:18px}.container{width:min(1500px,94vw);margin:24px auto}.hero{padding:24px 28px;border-radius:14px;background:linear-gradient(120deg,#17365d,#245f92);color:white;margin-bottom:18px}.hero.compact{padding:18px 24px}.hero h1,.hero p{margin:0 0 8px}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:#cbe5ff}.cards{display:grid;grid-template-columns:repeat(5,minmax(130px,1fr));gap:14px}.cards article,.panel{background:white;border:1px solid #d7e1eb;border-radius:12px;box-shadow:0 4px 16px rgba(23,54,93,.06)}.cards article{padding:18px}.cards span{display:block;color:#667085;font-size:13px}.cards strong{display:block;margin-top:7px;font-size:30px;color:#17365d}.panel{padding:18px;margin-top:18px}.action-panel{padding:24px}.button,button,.secondary{display:inline-block;border:0;border-radius:8px;padding:10px 14px;text-decoration:none;cursor:pointer}.button,button{background:#1f4e78;color:white}.secondary{background:#e9eef4;color:#17365d}.filters{display:grid;grid-template-columns:2fr 1fr auto auto;gap:10px;margin-bottom:18px}.filters input,.filters select,input[type=search]{width:100%;padding:10px 12px;border:1px solid #aebdca;border-radius:8px;background:white}.panel-title{display:flex;justify-content:space-between;align-items:center;gap:12px}.people-grid{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:12px}.person-card{display:flex;flex-direction:column;gap:5px;padding:14px;border:1px solid #d9e3ec;border-radius:10px;text-decoration:none;color:#172033;background:#fbfcfe}.person-card:hover{border-color:#1f4e78}.person-card span,.person-card small{color:#667085}.back{display:inline-block;margin-bottom:12px;color:#1f4e78}.profile-layout{display:grid;grid-template-columns:1fr 1fr;gap:18px}.chips{display:flex;gap:8px;flex-wrap:wrap}.chips span{padding:6px 10px;border-radius:999px;background:#e6f3ff;color:#174d7a}.stats{display:flex;gap:24px;flex-wrap:wrap}.stats span{color:#667085}.stats b{display:block;font-size:26px;color:#17365d}.table-wrap{overflow:auto;max-height:65vh}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #e6edf3;font-size:14px}th{position:sticky;top:0;background:#eef4fa;color:#17365d}.status{display:inline-block;padding:4px 8px;border-radius:999px}.status.permitido{background:#d9f5df;color:#075b24}.status.negado{background:#fde0df;color:#8a1712}.status.nao-identificado{background:#eef1f4;color:#475467}@media(max-width:950px){.cards{grid-template-columns:repeat(2,1fr)}.filters,.profile-layout{grid-template-columns:1fr}.people-grid{grid-template-columns:1fr}.topbar{align-items:flex-start;gap:12px;flex-direction:column}}'''

JS = '''document.querySelectorAll('[data-filter]').forEach(input=>{input.addEventListener('input',()=>{const q=input.value.toLocaleLowerCase('pt-BR');document.querySelectorAll(`#${input.dataset.filter} tbody tr`).forEach(row=>{row.style.display=row.innerText.toLocaleLowerCase('pt-BR').includes(q)?'':'none'})})});'''

(APP / 'main.py').write_text(MAIN, encoding='utf-8', newline='\n')
(TEMPLATES / 'base.html').write_text(BASE, encoding='utf-8', newline='\n')
(TEMPLATES / 'dashboard.html').write_text(DASHBOARD, encoding='utf-8', newline='\n')
(TEMPLATES / 'estrutura.html').write_text(ESTRUTURA, encoding='utf-8', newline='\n')
(TEMPLATES / 'funcionario.html').write_text(FUNCIONARIO, encoding='utf-8', newline='\n')
(STATIC / 'styles.css').write_text(CSS, encoding='utf-8', newline='\n')
(STATIC / 'app.js').write_text(JS, encoding='utf-8', newline='\n')
py_compile.compile(str(APP / 'main.py'), doraise=True)
print('Estrutura atual configurada com sucesso.')
print(r'Execute: uvicorn app.main:app --reload')
