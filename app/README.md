# Módulo de propostas de acesso

Implementação de referência em FastAPI + SQLAlchemy + Jinja2. Inclui árvore hierárquica, checkboxes de telas e botões, criação a partir de proposta, edição pelo solicitante, decisão pelo aprovador e exclusão lógica.

## Executar
1. `python -m venv .venv`
2. `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
3. `pip install -r requirements.txt`
4. `python run.py`
5. Abra `http://localhost:8000`

## Integração
Troque `usuario_atual()` pelo mecanismo real de autenticação. O exemplo inicia como usuário 1 (solicitante). Para testar aprovador, altere para `s.get(Usuario, 2)`. Migre os models para o banco e convenções do projeto antes de produção.
