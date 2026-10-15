from pathlib import Path
from datetime import datetime
import py_compile
import shutil

ROOT = Path.cwd().resolve()
ACCESS = ROOT / 'app' / 'access_control.py'
TEMPLATE = ROOT / 'app' / 'templates' / 'proposal_new.html'
JS = ROOT / 'app' / 'static' / 'proposals.js'
FILES = [ACCESS, TEMPLATE, JS]

missing = [str(p) for p in FILES if not p.exists()]
if missing:
    raise SystemExit('ERRO: arquivos não encontrados; nada foi alterado: ' + ', '.join(missing))

stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup = ROOT / f'backup_origens_proposta_{stamp}'
for source in FILES:
    target = backup / source.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

try:
    html = TEMPLATE.read_text(encoding='utf-8')

    select_start = html.find('<select name="origin" id="origin">')
    if select_start < 0:
        raise RuntimeError('Campo origin não encontrado em proposal_new.html')
    select_end = html.find('</select>', select_start)
    if select_end < 0:
        raise RuntimeError('Fechamento do campo origin não encontrado')
    select_end += len('</select>')

    new_select = '''<select name="origin" id="origin" required>
<option value="COPIADO_DE_PERFIL">Copiar perfil</option>
<option value="CONSOLIDADO_FUNCIONARIO">Consolidado de funcionário</option>
</select>'''
    html = html[:select_start] + new_select + html[select_end:]

    # Mantém os dois seletores no formulário; o JavaScript exibe somente o correspondente.
    if 'data-source="profile"' not in html or 'data-source="employee"' not in html:
        raise RuntimeError('Seletores de perfil e funcionário não encontrados no formulário')

    old_warning = 'A proposta será criada com a base escolhida. Na tela seguinte, use <b>Editar</b> para marcar telas e botões antes de enviar.'
    new_warning = 'Escolha entre <b>Copiar perfil</b> ou <b>Consolidado de funcionário</b>. Depois selecione o perfil ou funcionário desejado.'
    html = html.replace(old_warning, new_warning)
    TEMPLATE.write_text(html, encoding='utf-8', newline='\n')

    js = JS.read_text(encoding='utf-8')
    old_logic = "function sourceFields(){if(!origin)return;const v=origin.value;document.querySelectorAll('[data-source]').forEach(x=>x.classList.toggle('hidden-source',(x.dataset.source==='profile'&&v!=='COPIADO_DE_PERFIL')||(x.dataset.source==='employee'&&v!=='CONSOLIDADO_FUNCIONARIO')))}"
    new_logic = "function sourceFields(){if(!origin)return;const v=origin.value;document.querySelectorAll('[data-source]').forEach(x=>{const show=(x.dataset.source==='profile'&&v==='COPIADO_DE_PERFIL')||(x.dataset.source==='employee'&&v==='CONSOLIDADO_FUNCIONARIO');x.classList.toggle('hidden-source',!show);const select=x.querySelector('select');if(select){select.required=show;if(!show)select.value=''}})}"
    if old_logic not in js:
        raise RuntimeError('Lógica de origem esperada não encontrada em proposals.js')
    JS.write_text(js.replace(old_logic, new_logic, 1), encoding='utf-8', newline='\n')

    code = ACCESS.read_text(encoding='utf-8')
    marker = "def proposal_create("
    route_start = code.find(marker)
    if route_start < 0:
        raise RuntimeError('Função proposal_create não encontrada')
    route_end = code.find('\n@router.', route_start)
    if route_end < 0:
        route_end = len(code)
    block = code[route_start:route_end]

    old_validation = "if origin not in PROPOSAL_ORIGINS: raise HTTPException(400, 'Origem invalida')"
    new_validation = "if origin not in {'COPIADO_DE_PERFIL', 'CONSOLIDADO_FUNCIONARIO'}: raise HTTPException(400, 'Selecione Copiar perfil ou Consolidado de funcionario')"
    if old_validation in block:
        block = block.replace(old_validation, new_validation, 1)
    elif new_validation not in block:
        raise RuntimeError('Validação de origem não encontrada na criação da proposta')

    # Valida obrigatoriedade da base escolhida no backend.
    validation_anchor = new_validation
    required_validation = """
    if origin == 'COPIADO_DE_PERFIL' and not source_profile_id:
        raise HTTPException(400, 'Selecione o perfil que deseja copiar')
    if origin == 'CONSOLIDADO_FUNCIONARIO' and not source_employee_id:
        raise HTTPException(400, 'Selecione o funcionario que deseja consolidar')"""
    if "Selecione o perfil que deseja copiar" not in block:
        block = block.replace(validation_anchor, validation_anchor + required_validation, 1)

    code = code[:route_start] + block + code[route_end:]
    ACCESS.write_text(code, encoding='utf-8', newline='\n')
    py_compile.compile(str(ACCESS), doraise=True)

except Exception as exc:
    for source in FILES:
        saved = backup / source.relative_to(ROOT)
        if saved.exists():
            shutil.copy2(saved, source)
    raise SystemExit(f'ERRO: alteração cancelada e arquivos restaurados: {exc}')

print('Ajuste aplicado com sucesso.')
print('- Opções mantidas: Copiar perfil e Consolidado de funcionário')
print('- O seletor de perfil aparece ao escolher Copiar perfil')
print('- O seletor de funcionário aparece ao escolher Consolidado de funcionário')
print('- A base escolhida passou a ser obrigatória no navegador e no backend')
print('Backup:', backup)
