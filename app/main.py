from typing import Annotated

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
