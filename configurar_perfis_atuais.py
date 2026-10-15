from pathlib import Path
import py_compile

ROOT = Path.cwd()
MAIN_PATH = ROOT / "app" / "main.py"
TEMPLATES = ROOT / "app" / "templates"
CSS_PATH = ROOT / "app" / "static" / "styles.css"

if not MAIN_PATH.exists():
    raise SystemExit("app/main.py nao encontrado. Execute este arquivo na raiz do projeto.")

main = MAIN_PATH.read_text(encoding="utf-8")

route_code = r'''

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
def perfil_detalhe(request: Request, perfil_id: int, session: DatabaseSession):
    perfil = session.get(Perfil, perfil_id)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")

    usuarios = session.execute(
        select(Funcionario)
        .join(FuncionarioPerfil, FuncionarioPerfil.funcionario_id == Funcionario.id)
        .where(FuncionarioPerfil.perfil_id == perfil_id)
        .options(selectinload(Funcionario.departamento))
        .order_by(Funcionario.nome)
    ).scalars().all()

    acessos = session.execute(
        select(Acesso, PerfilAcesso.status)
        .join(PerfilAcesso, PerfilAcesso.acesso_id == Acesso.id)
        .where(PerfilAcesso.perfil_id == perfil_id)
        .order_by(
            Acesso.caminho_completo,
            Acesso.tela_final,
            Acesso.botao,
        )
    ).all()

    permitidos = sum(1 for _, status in acessos if str(status).casefold() == "permitido")
    negados = sum(1 for _, status in acessos if str(status).casefold() == "negado")

    return templates.TemplateResponse(
        request=request,
        name="perfil.html",
        context={
            "perfil": perfil,
            "usuarios": usuarios,
            "acessos": acessos,
            "permitidos": permitidos,
            "negados": negados,
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
'''

if '@app.get("/perfis", response_class=HTMLResponse)' not in main:
    main += route_code

MAIN_PATH.write_text(main, encoding="utf-8", newline="\n")

base_path = TEMPLATES / "base.html"
base = base_path.read_text(encoding="utf-8")
if 'href="/perfis"' not in base:
    base = base.replace(
        '<a href="/estrutura">Estrutura atual</a>',
        '<a href="/estrutura">Estrutura atual</a><a href="/perfis">Perfis atuais</a>',
    )
base_path.write_text(base, encoding="utf-8", newline="\n")

PERFIS_HTML = '''{% extends "base.html" %}
{% block title %}Perfis atuais{% endblock %}
{% block content %}
<section class="hero">
  <p class="eyebrow">Consulta</p>
  <h1>Perfis atuais</h1>
  <p>Perfis importados, usuarios vinculados e quantidade de acessos.</p>
</section>
<form class="filters profiles-filter" method="get">
  <input name="busca" value="{{ busca }}" placeholder="Pesquisar perfil">
  <select name="situacao">
    <option value="">Todas as situacoes</option>
    {% for item in situacoes %}
    <option value="{{ item }}" {% if item == situacao_selecionada %}selected{% endif %}>{{ item }}</option>
    {% endfor %}
  </select>
  <button type="submit">Filtrar</button>
  <a href="/perfis" class="secondary">Limpar</a>
</form>
<section class="profiles-grid">
  {% for perfil, usuarios, acessos in linhas %}
  <a class="profile-card" href="/perfis/{{ perfil.id }}">
    <div class="profile-card-title">
      <strong>{{ perfil.nome }}</strong>
      <span class="status">{{ perfil.situacao }}</span>
    </div>
    <div class="profile-numbers">
      <span><b>{{ usuarios }}</b> usuarios</span>
      <span><b>{{ acessos }}</b> acessos</span>
    </div>
    <small>Atualizado: {{ perfil.ultima_atualizacao or 'Nao informado' }}</small>
  </a>
  {% else %}
  <article class="panel">Nenhum perfil encontrado.</article>
  {% endfor %}
</section>
{% endblock %}
'''

PERFIL_HTML = '''{% extends "base.html" %}
{% block title %}{{ perfil.nome }}{% endblock %}
{% block content %}
<a class="back" href="/perfis">Voltar para perfis atuais</a>
<section class="hero compact">
  <p class="eyebrow">Perfil atual</p>
  <h1>{{ perfil.nome }}</h1>
  <p>Situacao: {{ perfil.situacao }} | Atualizacao: {{ perfil.ultima_atualizacao or 'Nao informada' }}</p>
</section>
<section class="profile-layout">
  <article class="panel">
    <h2>Resumo</h2>
    <div class="stats">
      <span><b>{{ usuarios|length }}</b> Usuarios</span>
      <span><b>{{ permitidos }}</b> Permitidos</span>
      <span><b>{{ negados }}</b> Negados</span>
      <span><b>{{ acessos|length }}</b> Total</span>
    </div>
  </article>
  <article class="panel">
    <div class="panel-title"><h2>Usuarios vinculados</h2><input type="search" placeholder="Pesquisar usuario" data-filter="profile-users"></div>
    <div class="table-wrap small-table">
      <table id="profile-users">
        <thead><tr><th>Nome</th><th>Login</th><th>Departamento</th></tr></thead>
        <tbody>
          {% for usuario in usuarios %}
          <tr><td>{{ usuario.nome }}</td><td>{{ usuario.login }}</td><td>{{ usuario.departamento.nome if usuario.departamento else 'Nao definido' }}</td></tr>
          {% else %}<tr><td colspan="3">Nenhum usuario vinculado.</td></tr>{% endfor %}
        </tbody>
      </table>
    </div>
  </article>
</section>
<section class="panel">
  <div class="panel-title"><h2>Acessos do perfil</h2><input type="search" placeholder="Pesquisar acesso" data-filter="profile-accesses"></div>
  <div class="table-wrap">
    <table id="profile-accesses">
      <thead><tr><th>Botao</th><th>Tela</th><th>Caminho</th><th>Status</th></tr></thead>
      <tbody>
        {% for acesso, status in acessos %}
        <tr>
          <td>{{ acesso.botao }}</td><td>{{ acesso.tela_final }}</td><td>{{ acesso.caminho_completo }}</td>
          <td><span class="status {{ status|lower|replace(' ','-') }}">{{ status }}</span></td>
        </tr>
        {% else %}<tr><td colspan="4">Nenhum acesso registrado.</td></tr>{% endfor %}
      </tbody>
    </table>
  </div>
</section>
{% endblock %}
'''

(TEMPLATES / "perfis.html").write_text(PERFIS_HTML, encoding="utf-8", newline="\n")
(TEMPLATES / "perfil.html").write_text(PERFIL_HTML, encoding="utf-8", newline="\n")

css = CSS_PATH.read_text(encoding="utf-8")
extra_css = '''
.profiles-grid{display:grid;grid-template-columns:repeat(3,minmax(240px,1fr));gap:14px}.profile-card{display:block;padding:17px;background:#fff;border:1px solid #d7e1eb;border-radius:12px;color:#172033;text-decoration:none;box-shadow:0 4px 16px rgba(23,54,93,.05)}.profile-card:hover{border-color:#1f4e78;transform:translateY(-1px)}.profile-card-title{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.profile-card-title strong{font-size:17px}.profile-numbers{display:flex;gap:22px;margin:18px 0}.profile-numbers span{color:#667085}.profile-numbers b{display:block;font-size:24px;color:#17365d}.profile-card small{color:#667085}.small-table{max-height:320px}.profiles-filter{grid-template-columns:2fr 1fr auto auto}@media(max-width:950px){.profiles-grid{grid-template-columns:1fr}.profiles-filter{grid-template-columns:1fr}}
'''
if ".profiles-grid" not in css:
    css += extra_css
CSS_PATH.write_text(css, encoding="utf-8", newline="\n")

py_compile.compile(str(MAIN_PATH), doraise=True)
print("Tela Perfis atuais configurada com sucesso.")
print(r"Execute: uvicorn app.main:app --reload")
