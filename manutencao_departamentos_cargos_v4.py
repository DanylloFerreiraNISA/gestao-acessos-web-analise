from __future__ import annotations
import py_compile, re, shutil, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
ACCESS = ROOT / 'app' / 'access_control.py'
T = ROOT / 'app' / 'templates'
BASE, DEPARTMENTS, MANAGE = T/'base.html', T/'departments.html', T/'department_manage_v3.html'
OPTIONAL = [T/'funcionario.html', T/'portal_employee.html', T/'portal_employee_edit.html']
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
BACKUP = ROOT / f'backup_manutencao_departamentos_cargos_{STAMP}'
MARK = 'MANUTENCAO_DEPARTAMENTOS_CARGOS_V4'
required = [ACCESS, BASE, DEPARTMENTS, MANAGE]
missing = [str(p) for p in required if not p.is_file()]
if missing:
    raise RuntimeError('Arquivos obrigatorios ausentes: ' + ', '.join(missing))
files = required + [p for p in OPTIONAL if p.is_file()]
for p in files:
    d = BACKUP / p.relative_to(ROOT); d.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, d)
original = {p: p.read_text(encoding='utf-8-sig') for p in files}
updated = dict(original)
try:
    access = updated[ACCESS]
    old = 'selected_cargo = session.get(Cargo, cargo_id) if cargo_id else (cargos[0] if cargos else None)'
    new = 'selected_cargo = session.get(Cargo, cargo_id) if cargo_id else None'
    if old not in access and new not in access:
        raise RuntimeError('Selecao automatica do primeiro cargo nao localizada em access_control.py')
    access = access.replace(old, new, 1)
    access = access.replace("f'/admin/cadastros/departamentos/{department_id}/painel?aba=cargos&cargo_id={cargo.id}',", "f'/admin/cadastros/departamentos/{department_id}/painel?aba=cargos',", 1)
    if MARK not in access:
        access = access.rstrip() + f'\n\n# {MARK}\n'
    updated[ACCESS] = access

    base = updated[BASE]
    base = re.sub(r'\s*<a href="/portal/departamentos">Departamentos</a>', '', base, count=1)
    base = re.sub(r'\s*<a href="/admin/departamentos">Departamentos</a>', '', base, count=1)
    updated[BASE] = base

    departments = updated[DEPARTMENTS]
    departments = re.sub(r'(<a class="button small" href="/admin/cadastros/departamentos/\{\{ item\.id \}\}/painel">Gerenciar</a>)\s*<a class="secondary-button small"[^>]*>Editar</a>', r'\1', departments, count=1)
    updated[DEPARTMENTS] = departments

    manage = updated[MANAGE]
    manage = re.sub(r'<div class="department-admin-actions">\s*<a[^>]+>Editar departamento</a>\s*</div>', '', manage, count=1)
    hero = '<section class="hero compact"><p class="eyebrow">Cadastro de departamento</p><h1>{{ department.nome }}</h1><p>Informe os usuarios do departamento e gerencie cargos em abas separadas.</p></section>'
    inline = hero + '\n' + '<section class="panel"><h2>Dados do departamento</h2><form method="post" action="/admin/cadastros/departamentos/{{ department.id }}/editar" class="integrated-form"><label>Nome do departamento<input name="nome" value="{{ department.nome }}" required maxlength="150"></label><label class="checkbox-field"><input type="checkbox" name="ativo" {% if department.ativo %}checked{% endif %}> Departamento ativo</label><div class="full form-actions"><button type="submit">Salvar departamento</button></div></form></section>'
    if hero in manage:
        manage = manage.replace(hero, inline, 1)
    elif 'Dados do departamento' not in manage:
        raise RuntimeError('Cabecalho esperado nao encontrado em department_manage_v3.html')
    manage = manage.replace('<a class="button small" href="?aba=cargos">Novo</a>', '<a class="button small" href="?aba=cargos&novo=1">Novo cargo</a>', 1)
    manage = manage.replace('href="?aba=cargos{% if selected_cargo %}&cargo_id={{ selected_cargo.id }}{% endif %}"', 'href="?aba=cargos"', 1)
    updated[MANAGE] = manage

    checks = {
        'cargo sem selecao automatica': new in updated[ACCESS],
        'menu antigo removido': '/portal/departamentos">Departamentos' not in updated[BASE] and '/admin/departamentos">Departamentos' not in updated[BASE],
        'botao editar removido': 'Editar departamento</a>' not in updated[MANAGE],
        'edicao inline': 'Dados do departamento' in updated[MANAGE],
        'novo cargo limpo': '?aba=cargos&novo=1' in updated[MANAGE],
    }
    failed = [k for k,v in checks.items() if not v]
    if failed: raise RuntimeError('Validacao falhou: ' + ', '.join(failed))
    for p, content in updated.items(): p.write_text(content, encoding='utf-8', newline='\n')
    py_compile.compile(str(ACCESS), doraise=True)
except Exception:
    for p in files:
        b = BACKUP / p.relative_to(ROOT)
        if b.is_file(): shutil.copy2(b, p)
    raise
print('\n[SUCESSO] Manutencao aplicada.')
print('[OK] Tela antiga removida do menu e botoes separados eliminados.')
print('[OK] Nome e situacao do departamento editaveis na tela principal.')
print('[OK] Nenhum cargo abre selecionado por padrao.')
print('[OK] Novo cargo abre formulario vazio.')
print('[OK] Vinculos de usuarios, departamentos e cargos preservados.')
print(f'[BACKUP] {BACKUP}')
print('\nReinicie o servidor e pressione Ctrl+F5.')
