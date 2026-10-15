from pathlib import Path
from datetime import datetime

ROOT = Path.cwd().resolve()
if not (ROOT / 'app').is_dir():
    raise SystemExit('ERRO: execute na raiz do gestao-acessos-web, onde existe a pasta app.')

candidates = [
    ROOT / 'app' / 'templates' / 'perfil.html',
    ROOT / 'app' / 'templates' / 'profile.html',
    ROOT / 'app' / 'templates' / 'portal_profile.html',
    ROOT / 'app' / 'templates' / 'base.html',
    ROOT / 'app' / 'templates' / 'proposal_new.html',
    ROOT / 'app' / 'templates' / 'proposal_edit.html',
    ROOT / 'app' / 'static' / 'classic-tree.js',
    ROOT / 'app' / 'static' / 'styles.css',
    ROOT / 'app' / 'static' / 'portal.css',
    ROOT / 'app' / 'static' / 'proposals.css',
    ROOT / 'app' / 'static' / 'proposals.js',
    ROOT / 'app' / 'access_control.py',
]
files = [p for p in candidates if p.is_file()]
if not files:
    raise SystemExit('ERRO: nenhum arquivo da árvore foi encontrado. Nada foi alterado.')

out = ROOT / f'arvore_real_perfis_{datetime.now():%Y%m%d_%H%M%S}.txt'
with out.open('w', encoding='utf-8', newline='\n') as target:
    target.write('COLETA SOMENTE LEITURA - ARVORE REAL DE PERFIS\n')
    target.write('Nenhum arquivo do sistema foi modificado.\n\n')
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        target.write(f'===== INICIO {relative} =====\n')
        target.write(path.read_text(encoding='utf-8'))
        target.write(f'\n===== FIM {relative} =====\n\n')

print('Coleta concluída sem alterar o sistema.')
print('Arquivo gerado:', out)
print('Arquivos coletados:', len(files))
