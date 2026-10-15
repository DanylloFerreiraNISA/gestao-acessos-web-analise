from __future__ import annotations
import subprocess, sys, py_compile
from pathlib import Path

root = Path.cwd()
v2 = root / 'atualizar_fluxo_perfil_aprovado_v2.py'
if not v2.exists():
    raise RuntimeError(f'Arquivo necessario nao encontrado: {v2}')

text = v2.read_text(encoding='utf-8-sig')
start_marker = '# 2) Aprovar:'
end_marker = '# 3) Lista atual'
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise RuntimeError('Nao foi possivel localizar a secao de aprovacao no atualizador V2.')

replacement = r'''# 2) Aprovar: localiza a funcao pelo mapeamento de status, sem depender da rota.
if "Perfil gerado na proposta" not in source:
    mapping_pos = source.find("mapping = {'aprovar':")
    if mapping_pos < 0:
        mapping_pos = source.find('mapping = {"aprovar":')
    if mapping_pos < 0:
        fail("O mapeamento de aprovar/rejeitar/devolver nao foi encontrado. Nenhum arquivo foi alterado.")

    function_start = source.rfind("\ndef ", 0, mapping_pos)
    function_end = source.find("\n@router.", mapping_pos)
    if function_start < 0:
        fail("A funcao administrativa nao foi localizada. Nenhum arquivo foi alterado.")
    if function_end < 0:
        function_end = len(source)
    block = source[function_start:function_end]

    reviewed = re.search(
        r"(?m)^(?P<i>\s*)proposal\.reviewed_at\s*=\s*datetime\.now\(timezone\.utc\)\s*$",
        block,
    )
    if not reviewed:
        fail("A linha reviewed_at da aprovacao nao foi encontrada. Nenhum arquivo foi alterado.")
    indent = reviewed.group('i')
    approval = f"""

{indent}if action == 'aprovar':
{indent}    proposal = session.scalar(
{indent}        select(ProfileProposal)
{indent}        .options(selectinload(ProfileProposal.accesses))
{indent}        .where(ProfileProposal.id == proposal_id)
{indent}    )
{indent}    if proposal.imported_result_profile_id is None:
{indent}        existing_profile = session.scalar(
{indent}            select(Perfil).where(func.lower(Perfil.nome) == proposal.name.strip().lower())
{indent}        )
{indent}        if existing_profile:
{indent}            raise HTTPException(409, 'Ja existe um perfil com este nome')
{indent}        generated_profile = Perfil(
{indent}            nome=proposal.name.strip(), situacao='Ativo',
{indent}            departamento_id=proposal.department_id,
{indent}            ultima_atualizacao=datetime.now(timezone.utc),
{indent}        )
{indent}        session.add(generated_profile)
{indent}        session.flush()
{indent}        for proposal_access in proposal.accesses:
{indent}            session.add(PerfilAcesso(
{indent}                perfil_id=generated_profile.id,
{indent}                acesso_id=proposal_access.access_id,
{indent}                status=proposal_access.status or 'Permitido',
{indent}            ))
{indent}        proposal.imported_result_profile_id = generated_profile.id
{indent}    details = ((details.strip() + ' | ') if details.strip() else '') + 'Perfil gerado na proposta'
"""
    block = block[:reviewed.end()] + approval + block[reviewed.end():]
    source = source[:function_start] + block + source[function_end:]
    print('[OK] aprovacao gera perfil com os acessos selecionados')
else:
    print('[OK] geracao do perfil ja estava aplicada')

'''

patched = text[:start] + replacement + text[end:]
temp = root / '_atualizador_fluxo_perfil_v3_execucao.py'
temp.write_text(patched, encoding='utf-8')
py_compile.compile(str(temp), doraise=True)
try:
    result = subprocess.run([sys.executable, str(temp)], cwd=root)
    raise SystemExit(result.returncode)
finally:
    temp.unlink(missing_ok=True)
