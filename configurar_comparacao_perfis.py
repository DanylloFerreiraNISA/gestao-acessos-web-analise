from pathlib import Path
import py_compile

ROOT = Path.cwd()
MAIN = ROOT / 'app' / 'main.py'
TEMPLATES = ROOT / 'app' / 'templates'
STATIC = ROOT / 'app' / 'static'

if not MAIN.exists():
    raise SystemExit('app/main.py nao encontrado. Execute na raiz do projeto.')

text = MAIN.read_text(encoding='utf-8')
code = r'''


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
'''

if '@app.get("/comparar", response_class=HTMLResponse)' not in text:
    text += code
MAIN.write_text(text, encoding='utf-8', newline='\n')

base_path = TEMPLATES / 'base.html'
base = base_path.read_text(encoding='utf-8')
if 'href="/comparar"' not in base:
    base = base.replace('<a href="/docs">API</a>', '<a href="/comparar">Comparar perfis</a><a href="/docs">API</a>')
base_path.write_text(base, encoding='utf-8', newline='\n')

html = '''{% extends "base.html" %}
{% block title %}Comparar perfis{% endblock %}
{% block content %}
<section class="hero">
  <p class="eyebrow">Analise</p>
  <h1>Comparar perfis</h1>
  <p>Compare dois perfis atuais e filtre as diferencas encontradas.</p>
</section>
<form class="compare-form" method="get">
  <label>Perfil A<select name="perfil_a" required><option value="">Selecione</option>{% for item in perfis %}<option value="{{ item.id }}" {% if perfil_a and item.id == perfil_a.id %}selected{% endif %}>{{ item.nome }}</option>{% endfor %}</select></label>
  <label>Perfil B<select name="perfil_b" required><option value="">Selecione</option>{% for item in perfis %}<option value="{{ item.id }}" {% if perfil_b and item.id == perfil_b.id %}selected{% endif %}>{{ item.nome }}</option>{% endfor %}</select></label>
  <label>Pesquisar<input name="busca" value="{{ busca }}" placeholder="Tela, botao ou caminho"></label>
  <label>Exibir<select name="categoria"><option value="todos">Todos</option><option value="manter" {% if categoria == 'manter' %}selected{% endif %}>Manter</option><option value="adicionar" {% if categoria == 'adicionar' %}selected{% endif %}>Adicionar</option><option value="remover" {% if categoria == 'remover' %}selected{% endif %}>Remover</option></select></label>
  <button type="submit">Comparar</button><a class="secondary" href="/comparar">Limpar</a>
</form>
{% if resultado %}
<section class="compare-summary">
  <article class="keep"><span>Manter</span><strong>{{ resultado.manter|length }}</strong></article>
  <article class="add"><span>Adicionar</span><strong>{{ resultado.adicionar|length }}</strong></article>
  <article class="remove"><span>Remover</span><strong>{{ resultado.remover|length }}</strong></article>
</section>
{% for titulo, nome, classe in [('Manter','manter','keep'),('Adicionar','adicionar','add'),('Remover','remover','remove')] %}
<section class="panel compare-section {{ classe }}">
  <div class="panel-title"><h2>{{ titulo }}</h2><span>{{ resultado[nome]|length }} itens</span></div>
  <div class="table-wrap"><table><thead><tr><th>Botao</th><th>Tela</th><th>Caminho</th><th>{{ perfil_a.nome }}</th><th>{{ perfil_b.nome }}</th></tr></thead><tbody>
  {% for item in resultado[nome] %}<tr><td>{{ item.botao }}</td><td>{{ item.tela }}</td><td>{{ item.caminho }}</td><td>{{ item.status_a }}</td><td>{{ item.status_b }}</td></tr>{% else %}<tr><td colspan="5">Nenhum item.</td></tr>{% endfor %}
  </tbody></table></div>
</section>
{% endfor %}
{% else %}
<section class="panel"><p>Selecione os dois perfis para iniciar a comparacao.</p></section>
{% endif %}
{% endblock %}
'''
(TEMPLATES / 'comparar.html').write_text(html, encoding='utf-8', newline='\n')

css_path = STATIC / 'styles.css'
css = css_path.read_text(encoding='utf-8')
extra = '''
.compare-form{display:grid;grid-template-columns:1fr 1fr 1.3fr .8fr auto auto;gap:10px;align-items:end;margin-bottom:18px}.compare-form label{display:flex;flex-direction:column;gap:6px;font-size:13px;color:#475467}.compare-form select,.compare-form input{padding:10px 12px;border:1px solid #aebdca;border-radius:8px;background:#fff;min-width:0}.compare-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.compare-summary article{padding:18px;border-radius:12px;background:#fff;border:1px solid #d7e1eb}.compare-summary span{display:block;color:#667085}.compare-summary strong{font-size:30px}.compare-summary .keep{border-left:5px solid #15803d}.compare-summary .add{border-left:5px solid #2563eb}.compare-summary .remove{border-left:5px solid #dc2626}.compare-section.keep{border-left:5px solid #15803d}.compare-section.add{border-left:5px solid #2563eb}.compare-section.remove{border-left:5px solid #dc2626}@media(max-width:1100px){.compare-form{grid-template-columns:1fr 1fr}.compare-summary{grid-template-columns:1fr}}
'''
if '.compare-form' not in css:
    css += extra
css_path.write_text(css, encoding='utf-8', newline='\n')

py_compile.compile(str(MAIN), doraise=True)
print('Comparacao de perfis configurada com sucesso.')
print(r'Execute: uvicorn app.main:app --reload')
