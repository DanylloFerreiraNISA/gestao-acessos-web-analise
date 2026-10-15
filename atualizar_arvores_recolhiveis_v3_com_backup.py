from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PATHS = {
    "classic": ROOT / "app" / "static" / "classic-tree.js",
    "comparison": ROOT / "app" / "static" / "comparison.js",
    "profile": ROOT / "app" / "templates" / "portal_profile.html",
    "styles": ROOT / "app" / "static" / "styles.css",
}
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_arvores_recolhiveis_v3_{STAMP}"
MARK = "ARVORES_RECOLHIVEIS_V3"

missing = [str(path) for path in PATHS.values() if not path.is_file()]
if missing:
    raise RuntimeError("Arquivos nao encontrados: " + ", ".join(missing))

source = {name: path.read_text(encoding="utf-8-sig") for name, path in PATHS.items()}
if MARK in source["classic"]:
    print("[OK] A manutencao V3 ja esta instalada.")
    raise SystemExit(0)

# Nao continua sobre uma instalacao parcial anterior.
partial_markers = ("ARVORES_RECOLHIVEIS_V1", "ARVORES_RECOLHIVEIS_V2", "data-static-access-tree")
found_partial = [marker for marker in partial_markers if marker in source["classic"] or marker in source["profile"]]
if found_partial:
    raise RuntimeError(
        "Foi encontrada uma instalacao parcial anterior: " + ", ".join(found_partial) +
        ". Restaure o backup criado pela tentativa anterior antes de executar a V3."
    )

# 1. Arvores dinamicas do usuario e perfis: todas fechadas e controles por navegador.
classic = source["classic"]
classic, count = re.subn(r"details\.open\s*=\s*depth\s*===\s*0\s*;", "details.open=false;", classic, count=1)
if count != 1:
    raise RuntimeError("O estado inicial da arvore classica nao foi localizado. Nenhum arquivo foi alterado.")

# Insere os controles depois que toolbar e conhecido. Regex tolera espacos e quebras.
toolbar_pattern = re.compile(
    r"(?P<line>\s*const\s+toolbar\s*=\s*root\.previousElementSibling\?\.classList\.contains\('classic-toolbar'\)"
    r"\s*\?\s*root\.previousElementSibling\s*:\s*null\s*;)"
)
toolbar_match = toolbar_pattern.search(classic)
if not toolbar_match:
    raise RuntimeError("O toolbar da arvore classica nao foi localizado. Nenhum arquivo foi alterado.")
controls = """
      if(toolbar&&!toolbar.querySelector('[data-tree-expand-all]')){
        const controls=document.createElement('span');
        controls.className='tree-expand-controls';
        controls.innerHTML='<button type="button" class="secondary" data-tree-expand-all>Expandir tudo</button><button type="button" class="secondary" data-tree-collapse-all>Recolher tudo</button>';
        toolbar.appendChild(controls);
        controls.querySelector('[data-tree-expand-all]').addEventListener('click',()=>root.querySelectorAll('details').forEach(item=>item.open=true));
        controls.querySelector('[data-tree-collapse-all]').addEventListener('click',()=>root.querySelectorAll('details').forEach(item=>item.open=false));
      }"""
classic = classic[:toolbar_match.end()] + controls + classic[toolbar_match.end():]
classic = f"// {MARK}\n" + classic

# 2. Comparacao: preserva os botoes existentes e fecha todos os ramos na abertura.
comparison = source["comparison"]
comparison, count = re.subn(r"details\.open\s*=\s*depth\s*===\s*0\s*;", "details.open=false;", comparison, count=1)
if count != 1:
    raise RuntimeError("O estado inicial da arvore de comparacao nao foi localizado. Nenhum arquivo foi alterado.")

# 3. Perfil individual: remove 'open', cria conteiner e controles estaticos.
profile = source["profile"]
if "<details open>" not in profile:
    raise RuntimeError("Os detalhes abertos do perfil nao foram localizados. Nenhum arquivo foi alterado.")
profile = profile.replace("<details open>", "<details>")
heading_pattern = re.compile(r"(?P<indent>\s*)<h2>Árvore de acessos</h2>")
heading_match = heading_pattern.search(profile)
if not heading_match:
    raise RuntimeError("O titulo da arvore do perfil nao foi localizado. Nenhum arquivo foi alterado.")
indent = heading_match.group("indent")
replacement = (
    f'{indent}<div class="tree-panel-heading">\n'
    f'{indent}  <h2>Árvore de acessos</h2>\n'
    f'{indent}  <div class="tree-expand-controls">\n'
    f'{indent}    <button type="button" class="secondary" data-tree-expand-all>Expandir tudo</button>\n'
    f'{indent}    <button type="button" class="secondary" data-tree-collapse-all>Recolher tudo</button>\n'
    f'{indent}  </div>\n'
    f'{indent}</div>\n'
    f'{indent}<div class="static-access-tree" data-static-access-tree>'
)
profile = profile[:heading_match.start()] + replacement + profile[heading_match.end():]

end_pattern = re.compile(r"(?P<line>\s*{%\s*if\s+ns\.path_open\s*%}</div></details>{%\s*endif\s*%})")
end_matches = list(end_pattern.finditer(profile))
if not end_matches:
    raise RuntimeError("O final da arvore do perfil nao foi localizado. Nenhum arquivo foi alterado.")
last = end_matches[-1]
profile = profile[:last.end()] + f"\n{indent}</div>" + profile[last.end():]

# Pequeno controlador independente para a arvore estatica do perfil.
static_script = """
{% block scripts %}
{{ super() }}
<script>
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('[data-static-access-tree]').forEach(tree=>{
    tree.querySelectorAll('details').forEach(item=>item.open=false);
    const panel=tree.closest('.panel');
    panel?.querySelector('[data-tree-expand-all]')?.addEventListener('click',()=>tree.querySelectorAll('details').forEach(item=>item.open=true));
    panel?.querySelector('[data-tree-collapse-all]')?.addEventListener('click',()=>tree.querySelectorAll('details').forEach(item=>item.open=false));
  });
});
</script>
{% endblock %}
"""
if "{% endblock %}" not in profile:
    raise RuntimeError("O fim do template do perfil nao foi localizado. Nenhum arquivo foi alterado.")
profile = profile.rsplit("{% endblock %}", 1)[0].rstrip() + "\n{% endblock %}\n" + static_script

# 4. Estilos dos controles.
styles = source["styles"]
css = """

/* ARVORES_RECOLHIVEIS_V3 */
.tree-panel-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.tree-panel-heading h2{margin:0}
.tree-expand-controls{display:inline-flex;align-items:center;gap:7px;margin-left:auto}
.tree-expand-controls button{padding:7px 10px;font-size:13px;white-space:nowrap}
.static-access-tree{margin-top:12px}
.static-access-tree details{border:1px solid #dbe4ec;border-radius:8px;background:#fbfcfe;margin:6px 0;overflow:hidden}
.static-access-tree details>summary{cursor:pointer;padding:9px 11px;color:#17365d}
.static-access-tree details>div,.static-access-tree details>ul{margin:0;padding:4px 12px 10px 26px}
@media(max-width:700px){.tree-expand-controls{width:100%;margin-left:0}.tree-expand-controls button{flex:1}}
"""
styles = styles.rstrip() + css

updated = {"classic": classic, "comparison": comparison, "profile": profile, "styles": styles}
checks = {
    "classic": [MARK, "details.open=false", "data-tree-expand-all", "data-tree-collapse-all"],
    "comparison": ["details.open=false", "expand-all", "collapse-all"],
    "profile": ["data-static-access-tree", "data-tree-expand-all", "data-tree-collapse-all", "tree.querySelectorAll('details')"],
    "styles": ["ARVORES_RECOLHIVEIS_V3", ".tree-expand-controls"],
}
for name, markers in checks.items():
    absent = [marker for marker in markers if marker not in updated[name]]
    if absent:
        raise RuntimeError(f"Falha ao preparar {PATHS[name]}: {', '.join(absent)}. Nenhum arquivo foi alterado.")

# Backup antes de qualquer escrita.
for path in PATHS.values():
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)

try:
    for name, path in PATHS.items():
        path.write_text(updated[name], encoding="utf-8")
    for name, markers in checks.items():
        written = PATHS[name].read_text(encoding="utf-8")
        absent = [marker for marker in markers if marker not in written]
        if absent:
            raise RuntimeError(f"Validacao final falhou em {PATHS[name]}: {', '.join(absent)}")
except Exception:
    for path in PATHS.values():
        saved = BACKUP / path.relative_to(ROOT)
        if saved.exists():
            shutil.copy2(saved, path)
    raise

print("\n[SUCESSO] Arvores recolhiveis V3 instaladas.")
print("[OK] Arvores dinamicas iniciam fechadas.")
print("[OK] Arvore do perfil individual inicia fechada.")
print("[OK] Expandir tudo e Recolher tudo foram adicionados.")
print("[OK] Comparacao preserva os controles existentes.")
print(f"[BACKUP] {BACKUP}")
print("\nReinicie o servidor e use Ctrl+F5 no navegador.")
