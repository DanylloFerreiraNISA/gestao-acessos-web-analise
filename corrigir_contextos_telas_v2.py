from pathlib import Path
import py_compile

MAIN = Path('app/main.py')
if not MAIN.exists():
    raise SystemExit('Execute na raiz do projeto: C:\\Projetos\\gestao-acessos-web')

text = MAIN.read_text(encoding='utf-8')

HELPERS = '''def acessos_serializados_perfil(session: Session, perfil_id: int):
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
'''

FUNC_ROUTE = '''@app.get("/funcionarios/{funcionario_id}", response_class=HTMLResponse)
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
'''

PERFIL_ROUTE = '''@app.get("/perfis/{perfil_id}", response_class=HTMLResponse)
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
'''


def replace_function(source: str, function_name: str, replacement: str) -> str:
    lines = source.splitlines(keepends=True)
    def_index = next(
        (i for i, line in enumerate(lines) if line.startswith(f'def {function_name}(')),
        None,
    )
    if def_index is None:
        raise SystemExit(f'Funcao {function_name} nao encontrada em app/main.py.')

    start = def_index
    while start > 0 and lines[start - 1].lstrip().startswith('@'):
        start -= 1

    end = len(lines)
    for i in range(def_index + 1, len(lines)):
        if lines[i].startswith('@app.') or lines[i].startswith('def '):
            end = i
            break

    new_lines = lines[:start] + [replacement.rstrip() + '\n\n'] + lines[end:]
    return ''.join(new_lines)


# Insere os helpers antes da primeira rota, sem depender da ordem atual do arquivo.
if 'def acessos_serializados_perfil(' not in text:
    pos = text.find('@app.')
    if pos < 0:
        raise SystemExit('Nenhuma rota @app encontrada em app/main.py.')
    text = text[:pos] + HELPERS.rstrip() + '\n\n\n' + text[pos:]

text = replace_function(text, 'funcionario_detalhe', FUNC_ROUTE)
text = replace_function(text, 'perfil_detalhe', PERFIL_ROUTE)

MAIN.write_text(text, encoding='utf-8', newline='\n')
py_compile.compile(str(MAIN), doraise=True)

print('Correcao geral aplicada com sucesso.')
print('- Tela de funcionario: consolidado + acessos por perfil')
print('- Tela de perfil: acessos serializados + usuarios')
print('- Consolidado: Permitido prevalece sobre Negado')
print('- app/main.py: sintaxe validada')
