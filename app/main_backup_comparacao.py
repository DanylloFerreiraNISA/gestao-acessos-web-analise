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


def acessos_serializados_perfil(session: Session, perfil_id: int):
    linhas = session.execute(
        select(Acesso, PerfilAcesso.status)
        .join(PerfilAcesso, PerfilAcesso.acesso_id == Acesso.id)
        .where(PerfilAcesso.perfil_id == perfil_id)
        .order_by(Acesso.caminho_completo, Acesso.tela_final, Acesso.botao)
    ).all()
    return [
        {
            "id": acesso.id,
            "caminho": acesso.caminho_completo,
            "tela": acesso.tela_final,
            "botao": acesso.botao,
            "status": status,
        }
        for acesso, status in linhas
    ]


def consolidado_serializado_funcionario(session: Session, funcionario_id: int):
    linhas = session.execute(
        select(Acesso, PerfilAcesso.status, Perfil.nome.label("perfil_nome"))
        .join(PerfilAcesso, PerfilAcesso.acesso_id == Acesso.id)
        .join(Perfil, Perfil.id == PerfilAcesso.perfil_id)
        .join(FuncionarioPerfil, FuncionarioPerfil.perfil_id == Perfil.id)
        .where(FuncionarioPerfil.funcionario_id == funcionario_id)
    ).all()

    agrupado = {}
    for acesso, status, perfil_nome in linhas:
        item = agrupado.setdefault(
            acesso.id,
            {
                "id": acesso.id,
                "caminho": acesso.caminho_completo,
                "tela": acesso.tela_final,
                "botao": acesso.botao,
                "status": "Nao identificado",
                "perfis": [],
            },
        )
        item["perfis"].append({"nome": perfil_nome, "status": status})
        normalizado = str(status or "").strip().casefold()
        if normalizado == "permitido":
            item["status"] = "Permitido"
        elif item["status"] != "Permitido" and normalizado == "negado":
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
def funcionario_detalhe(
    request: Request,
    funcionario_id: int,
    session: DatabaseSession,
):
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

    por_perfil = [
        {
            "perfil": vinculo.perfil,
            "acessos": acessos_serializados_perfil(session, vinculo.perfil.id),
        }
        for vinculo in sorted(
            funcionario.perfis,
            key=lambda item: item.perfil.nome.casefold(),
        )
    ]

    return templates.TemplateResponse(
        request=request,
        name="funcionario.html",
        context={
            "funcionario": funcionario,
            "consolidado": consolidado_serializado_funcionario(session, funcionario_id),
            "por_perfil": por_perfil,
        },
    )

@app.get("/perfis", response_class=HTMLResponse)
def perfis_atuais(
    request: Request,
    session: DatabaseSession,
    busca: str = "",
    situacao: str = "",
):
    contagem_usuarios = (
        select(
            FuncionarioPerfil.perfil_id.label("perfil_id"),
            func.count(FuncionarioPerfil.id).label("usuarios"),
        )
        .group_by(FuncionarioPerfil.perfil_id)
        .subquery()
    )
    contagem_acessos = (
        select(
            PerfilAcesso.perfil_id.label("perfil_id"),
            func.count(PerfilAcesso.id).label("acessos"),
        )
        .group_by(PerfilAcesso.perfil_id)
        .subquery()
    )
    stmt = (
        select(
            Perfil,
            func.coalesce(contagem_usuarios.c.usuarios, 0).label("usuarios"),
            func.coalesce(contagem_acessos.c.acessos, 0).label("acessos"),
        )
        .outerjoin(contagem_usuarios, contagem_usuarios.c.perfil_id == Perfil.id)
        .outerjoin(contagem_acessos, contagem_acessos.c.perfil_id == Perfil.id)
        .order_by(Perfil.nome)
    )
    if busca.strip():
        stmt = stmt.where(Perfil.nome.ilike(f"%{busca.strip()}%"))
    if situacao.strip():
        stmt = stmt.where(Perfil.situacao == situacao.strip())

    linhas = session.execute(stmt).all()
    situacoes = session.scalars(
        select(Perfil.situacao).distinct().order_by(Perfil.situacao)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="perfis.html",
        context={
            "linhas": linhas,
            "busca": busca,
            "situacao_selecionada": situacao,
            "situacoes": situacoes,
        },
    )


@app.get("/perfis/{perfil_id}", response_class=HTMLResponse)
def perfil_detalhe(
    request: Request,
    perfil_id: int,
    session: DatabaseSession,
):
    perfil = session.get(Perfil, perfil_id)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")

    usuarios = session.scalars(
        select(Funcionario)
        .join(FuncionarioPerfil, FuncionarioPerfil.funcionario_id == Funcionario.id)
        .where(FuncionarioPerfil.perfil_id == perfil_id)
        .options(selectinload(Funcionario.departamento))
        .order_by(Funcionario.nome)
    ).all()
    acessos = acessos_serializados_perfil(session, perfil_id)

    return templates.TemplateResponse(
        request=request,
        name="perfil.html",
        context={
            "perfil": perfil,
            "usuarios": usuarios,
            "acessos": acessos,
            "permitidos": sum(1 for item in acessos if str(item["status"] or "").casefold() == "permitido"),
            "negados": sum(1 for item in acessos if str(item["status"] or "").casefold() == "negado"),
        },
    )

@app.get("/api/perfis/{perfil_id}")
def api_perfil_detalhe(perfil_id: int, session: DatabaseSession):
    perfil = session.get(Perfil, perfil_id)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")

    usuarios = session.execute(
        select(Funcionario.login, Funcionario.nome)
        .join(FuncionarioPerfil, FuncionarioPerfil.funcionario_id == Funcionario.id)
        .where(FuncionarioPerfil.perfil_id == perfil_id)
        .order_by(Funcionario.nome)
    ).all()
    acessos = session.execute(
        select(
            Acesso.caminho_completo,
            Acesso.tela_final,
            Acesso.botao,
            PerfilAcesso.status,
        )
        .join(PerfilAcesso, PerfilAcesso.acesso_id == Acesso.id)
        .where(PerfilAcesso.perfil_id == perfil_id)
        .order_by(Acesso.caminho_completo, Acesso.tela_final, Acesso.botao)
    ).all()
    return {
        "id": perfil.id,
        "nome": perfil.nome,
        "situacao": perfil.situacao,
        "ultima_atualizacao": perfil.ultima_atualizacao,
        "usuarios": [{"login": row.login, "nome": row.nome} for row in usuarios],
        "acessos": [
            {
                "caminho": row.caminho_completo,
                "tela": row.tela_final,
                "botao": row.botao,
                "status": row.status,
            }
            for row in acessos
        ],
    }



def mapa_perfil(session: Session, perfil_id: int):
    rows = session.execute(
        select(Acesso, PerfilAcesso.status)
        .join(PerfilAcesso, PerfilAcesso.acesso_id == Acesso.id)
        .where(PerfilAcesso.perfil_id == perfil_id)
    ).all()
    return {
        acesso.id: {
            "id": acesso.id,
            "caminho": acesso.caminho_completo,
            "tela": acesso.tela_final,
            "botao": acesso.botao,
            "status": status,
        }
        for acesso, status in rows
    }


def comparar_mapas(mapa_a, mapa_b):
    ids_a = set(mapa_a)
    ids_b = set(mapa_b)
    manter = []
    adicionar = []
    remover = []

    for acesso_id in ids_a | ids_b:
        a = mapa_a.get(acesso_id)
        b = mapa_b.get(acesso_id)
        if a and b:
            item = dict(a)
            item["status_a"] = a["status"]
            item["status_b"] = b["status"]
            if str(a["status"]).casefold() == str(b["status"]).casefold():
                item["categoria"] = "manter"
                manter.append(item)
            elif str(a["status"]).casefold() == "permitido":
                item["categoria"] = "adicionar"
                adicionar.append(item)
            else:
                item["categoria"] = "remover"
                remover.append(item)
        elif a:
            item = dict(a)
            item["status_a"] = a["status"]
            item["status_b"] = "Ausente"
            item["categoria"] = "adicionar"
            adicionar.append(item)
        else:
            item = dict(b)
            item["status_a"] = "Ausente"
            item["status_b"] = b["status"]
            item["categoria"] = "remover"
            remover.append(item)

    ordenar = lambda x: (x["caminho"].casefold(), x["tela"].casefold(), x["botao"].casefold())
    return {
        "manter": sorted(manter, key=ordenar),
        "adicionar": sorted(adicionar, key=ordenar),
        "remover": sorted(remover, key=ordenar),
    }


@app.get("/comparar", response_class=HTMLResponse)
def comparar_perfis(
    request: Request,
    session: DatabaseSession,
    perfil_a: int | None = None,
    perfil_b: int | None = None,
    busca: str = "",
    categoria: str = "todos",
):
    perfis = session.scalars(select(Perfil).order_by(Perfil.nome)).all()
    resultado = None
    selecionado_a = session.get(Perfil, perfil_a) if perfil_a else None
    selecionado_b = session.get(Perfil, perfil_b) if perfil_b else None

    if selecionado_a and selecionado_b:
        resultado = comparar_mapas(
            mapa_perfil(session, selecionado_a.id),
            mapa_perfil(session, selecionado_b.id),
        )
        termo = busca.strip().casefold()
        if termo:
            for nome in resultado:
                resultado[nome] = [
                    item for item in resultado[nome]
                    if termo in " ".join((item["caminho"], item["tela"], item["botao"])).casefold()
                ]
        if categoria in {"manter", "adicionar", "remover"}:
            for nome in list(resultado):
                if nome != categoria:
                    resultado[nome] = []

    return templates.TemplateResponse(
        request=request,
        name="comparar.html",
        context={
            "perfis": perfis,
            "perfil_a": selecionado_a,
            "perfil_b": selecionado_b,
            "resultado": resultado,
            "busca": busca,
            "categoria": categoria,
        },
    )


@app.get("/api/comparar")
def api_comparar(perfil_a: int, perfil_b: int, session: DatabaseSession):
    a = session.get(Perfil, perfil_a)
    b = session.get(Perfil, perfil_b)
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")
    resultado = comparar_mapas(mapa_perfil(session, a.id), mapa_perfil(session, b.id))
    return {
        "perfil_a": {"id": a.id, "nome": a.nome},
        "perfil_b": {"id": b.id, "nome": b.nome},
        "totais": {nome: len(itens) for nome, itens in resultado.items()},
        "resultado": resultado,
    }
