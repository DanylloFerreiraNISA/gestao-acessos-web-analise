from typing import Annotated

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
