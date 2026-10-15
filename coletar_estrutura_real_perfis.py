from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd().resolve()
APP = ROOT / "app"
OUT = ROOT / "diagnostico_perfis_atual.txt"

if not APP.exists():
    raise RuntimeError(f"Pasta nao encontrada: {APP}")

sections: list[str] = []

def add(title: str, content: str) -> None:
    sections.append(f"\n{'=' * 90}\n{title}\n{'=' * 90}\n{content.rstrip()}\n")

# Rotas reais relacionadas a perfis e propostas.
for py_file in sorted(APP.rglob("*.py")):
    text = py_file.read_text(encoding="utf-8-sig", errors="replace")
    if not any(token in text for token in ("/perfis", "/portal/perfis", "ProfileProposal", "imported_result_profile_id")):
        continue

    lines = text.splitlines()
    indexes: set[int] = set()
    for i, line in enumerate(lines):
        if any(token in line for token in (
            "@router.get('/perfis", '@router.get("/perfis',
            "@router.post('/perfis", '@router.post("/perfis',
            "@router.get('/portal/perfis", '@router.get("/portal/perfis',
            "@router.post('/portal/perfis", '@router.post("/portal/perfis',
            "imported_result_profile_id", "mapping = {'aprovar'", 'mapping = {"aprovar"',
        )):
            indexes.update(range(max(0, i - 5), min(len(lines), i + 55)))

    if indexes:
        selected = []
        last = -2
        for i in sorted(indexes):
            if i > last + 1:
                selected.append("\n...\n")
            selected.append(f"{i + 1:05d}: {lines[i]}")
            last = i
        add(str(py_file.relative_to(ROOT)), "\n".join(selected))

# Templates reais com os textos vistos nas duas telas.
keywords = (
    "PERFIS IMPORTADOS DO ERP",
    "Todos os perfis disponíveis",
    "Todos os perfis disponiveis",
    "Perfis atuais",
    "perfil(is) encontrado",
    "Gerado na proposta",
    "/portal/perfis",
    "/perfis/",
    "Inativar perfil",
)
for html in sorted((APP / "templates").rglob("*.html")):
    text = html.read_text(encoding="utf-8-sig", errors="replace")
    if any(keyword.casefold() in text.casefold() for keyword in keywords):
        add(str(html.relative_to(ROOT)), text)

# CSS apenas para identificar classes usadas pela tela, sem copiar arquivos enormes por completo.
for css in sorted((APP / "static").rglob("*.css")):
    text = css.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.findall(r"[^{}]*(?:profile|perfil|card|tree)[^{}]*\{[^{}]*\}", text, flags=re.I)
    if blocks:
        add(str(css.relative_to(ROOT)), "\n\n".join(blocks))

OUT.write_text("".join(sections), encoding="utf-8")
print(f"[SUCESSO] Diagnostico criado: {OUT}")
print("Nenhum arquivo do sistema foi alterado.")
