from pathlib import Path
from datetime import datetime
import shutil

ROOT=Path.cwd().resolve(); T=ROOT/'app'/'templates'
files=[T/'proposals.html',T/'proposal_new.html',T/'proposal_detail.html',T/'proposal_edit.html']
missing=[str(p) for p in files+[T/'base.html'] if not p.exists()]
if missing: raise SystemExit('ERRO: arquivos ausentes; nada alterado: '+', '.join(missing))
backup=ROOT/f"backup_menu_propostas_{datetime.now():%Y%m%d_%H%M%S}"
for p in files:
 d=backup/p.relative_to(ROOT); d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,d)

def main_inner(html):
 start=html.find('<main>'); end=html.find('</main>',start)
 if start<0 or end<0: raise RuntimeError('Bloco <main> não encontrado')
 return html[start+6:end]

def dialog(html):
 marker="{% include '_proposal_delete_dialog.html' %}"
 return marker if marker in html else ''

def convert(path,title,has_dialog=False):
 html=path.read_text(encoding='utf-8')
 content=main_inner(html)
 extra=dialog(html) if has_dialog else ''
 out=f'''{{% extends "base.html" %}}
{{% block title %}}{title} | Gestão de Acessos{{% endblock %}}
{{% block head %}}<link rel="stylesheet" href="{{{{ url_for('static', path='/proposals.css') }}}}">{{% endblock %}}
{{% block content %}}
{content}
{extra}
{{% endblock %}}
{{% block scripts %}}<script src="{{{{ url_for('static', path='/proposals.js') }}}}"></script>{{% endblock %}}
'''
 path.write_text(out,encoding='utf-8',newline='\n')

try:
 convert(T/'proposals.html','Propostas',True)
 convert(T/'proposal_new.html','Nova proposta')
 convert(T/'proposal_detail.html','Detalhes da proposta',True)
 convert(T/'proposal_edit.html','Editar proposta')
except Exception as exc:
 for p in files: shutil.copy2(backup/p.relative_to(ROOT),p)
 raise SystemExit(f'ERRO: alteração cancelada e templates restaurados: {exc}')

print('Menu das telas de propostas unificado com base.html.')
print('As quatro telas agora usam o mesmo cabeçalho, escopo e logout do sistema.')
print('Backup:',backup)
