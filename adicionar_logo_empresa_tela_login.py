from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
APP = ROOT / "app"
TEMPLATES = APP / "templates"
STATIC = APP / "static"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_logo_login_{STAMP}"
MARKER = "LOGO_EMPRESA_TELA_LOGIN_V1"

# Coloque a imagem na raiz do projeto com um destes nomes.
LOGO_NAMES = (
    "logo_empresa.png",
    "logo_empresa.jpg",
    "logo_empresa.jpeg",
    "logo_empresa.webp",
    "logo_empresa.svg",
    "logo.png",
    "logo.jpg",
    "logo.svg",
)

if not TEMPLATES.exists():
    raise RuntimeError(f"Pasta de templates nao encontrada: {TEMPLATES}")

logo_source = next((ROOT / name for name in LOGO_NAMES if (ROOT / name).is_file()), None)
if logo_source is None:
    expected = "\n".join(f"  - {name}" for name in LOGO_NAMES[:5])
    raise RuntimeError(
        "A imagem da empresa nao foi encontrada na raiz do projeto.\n"
        "Salve a logo com um destes nomes e execute novamente:\n" + expected +
        "\nNenhum arquivo foi alterado."
    )

# Localiza o template real de login pelo formulario de senha.
candidates: list[tuple[int, Path]] = []
for template in TEMPLATES.rglob("*.html"):
    text = template.read_text(encoding="utf-8-sig", errors="ignore")
    lowered = text.lower()
    score = 0
    if 'type="password"' in lowered or "type='password'" in lowered:
        score += 100
    if "login" in lowered or "entrar" in lowered:
        score += 40
    if "username" in lowered or "usuario" in lowered or "usuário" in lowered:
        score += 20
    if "login" in template.name.lower():
        score += 30
    if score >= 100:
        candidates.append((score, template))

if not candidates:
    raise RuntimeError("O template da tela de login nao foi encontrado. Nenhum arquivo foi alterado.")

candidates.sort(key=lambda item: (-item[0], str(item[1])))
login_template = candidates[0][1]
html = login_template.read_text(encoding="utf-8-sig")

if MARKER in html:
    print(f"[OK] A logo ja esta instalada em {login_template.relative_to(ROOT)}")
    raise SystemExit(0)

logo_dir = STATIC / "images"
logo_target = logo_dir / f"logo_empresa{logo_source.suffix.lower()}"

# Bloco independente, sem depender das classes atuais do login.
logo_block = f'''\n<!-- {MARKER} -->
<div class="company-login-logo">
  <img src="{{{{ url_for('static', path='/images/{logo_target.name}') }}}}" alt="Logo da empresa">
</div>
<style>
.company-login-logo{{display:flex;justify-content:center;align-items:center;margin:0 auto 22px}}
.company-login-logo img{{display:block;max-width:min(280px,80vw);max-height:120px;width:auto;height:auto;object-fit:contain}}
@media(max-width:600px){{.company-login-logo img{{max-width:min(220px,75vw);max-height:90px}}}}
</style>
'''

# Insere antes do formulario para que a logo fique no topo do cartao de login.
form_match = re.search(r"<form\b", html, flags=re.I)
if not form_match:
    raise RuntimeError("O formulario do login nao foi encontrado no template. Nenhum arquivo foi alterado.")
html = html[:form_match.start()] + logo_block + html[form_match.start():]

# Cria os backups antes de gravar.
for path in (login_template,):
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
if logo_target.exists():
    destination = BACKUP / logo_target.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(logo_target, destination)

try:
    logo_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(logo_source, logo_target)
    login_template.write_text(html, encoding="utf-8")
except Exception:
    template_backup = BACKUP / login_template.relative_to(ROOT)
    if template_backup.exists():
        shutil.copy2(template_backup, login_template)
    logo_backup = BACKUP / logo_target.relative_to(ROOT)
    if logo_backup.exists():
        shutil.copy2(logo_backup, logo_target)
    elif logo_target.exists():
        logo_target.unlink()
    raise

print("\n[SUCESSO] Logo adicionada a tela de login.")
print(f"[TEMPLATE] {login_template.relative_to(ROOT)}")
print(f"[IMAGEM] {logo_target.relative_to(ROOT)}")
print(f"[BACKUP] {BACKUP}")
print("[PRESERVADO] Backend, banco de dados e demais telas nao foram alterados.")
print("\nReinicie o servidor e pressione Ctrl + F5.")
