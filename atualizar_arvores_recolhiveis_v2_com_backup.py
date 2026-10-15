from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TARGETS = {
    "classic": ROOT / "app" / "static" / "classic-tree.js",
    "comparison": ROOT / "app" / "static" / "comparison.js",
    "profile": ROOT / "app" / "templates" / "portal_profile.html",
    "styles": ROOT / "app" / "static" / "styles.css",
}
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f"backup_arvores_recolhiveis_v2_{STAMP}"
MARK = "ARVORES_RECOLHIVEIS_V2"

missing = [str(path) for path in TARGETS.values() if not path.exists()]
if missing:
    raise RuntimeError("Arquivos nao encontrados: " + ", ".join(missing))

sources = {name: path.read_text(encoding="utf-8-sig") for name, path in TARGETS.items()}
if MARK in sources["classic"]:
    print("[OK] A manutencao V2 das arvores ja esta instalada.")
    raise SystemExit(0)

# Confere a estrutura real antes de preparar qualquer alteracao.
required_markers = {
    "classic": ["ClassicAccessTree", "function branch", "function mountBrowser"],
    "comparison": ["comparison-data", "function branch", "expand-all", "collapse-all"],
    "profile": ["Árvore de acessos", "<details open>", "ns.path_open"],
    "styles": [".classic-tree", ".comparison-branch"],
}
for name, markers in required_markers.items():
    absent = [marker for marker in markers if marker not in sources[name]]
    if absent:
        raise RuntimeError(
            f"Estrutura nao reconhecida em {TARGETS[name]}: {', '.join(absent)}. "
            "Nenhum arquivo foi alterado."
        )

classic = sources["classic"]
classic = classic.replace("const ClassicAccessTree=(()=>{", f"// {MARK}\nconst ClassicAccessTree=(()=>{{", 1)
classic = classic.replace("details.open=depth===0;", "details.open=false;", 1)

mount_anchor = "      const toolbar=root.previousElementSibling?.classList.contains('classic-toolbar')?root.previousElementSibling:null;"
controls_block = """
      if(toolbar&&!toolbar.querySelector('[data-tree-expand-all]')){
        const controls=document.createElement('span');
        controls.className='tree-expand-controls';
        controls.innerHTML='<button type="button" class="secondary" data-tree-expand-all>Expandir tudo</button><button type="button" class="secondary" data-tree-collapse-all>Recolher tudo</button>';
        toolbar.appendChild(controls);
        controls.querySelector('[data-tree-expand-all]').addEventListener('click',()=>root.querySelectorAll('details').forEach(item=>item.open=true));
        controls.querySelector('[data-tree-collapse-all]').addEventListener('click',()=>root.querySelectorAll('details').forEach(item=>item.open=false));
      }
""".rstrip()
classic = classic.replace(mount_anchor, mount_anchor + controls_block, 1)

start_anchor = "    function start(){"
static_block = """
    function bindStaticTrees(){
      document.querySelectorAll('[data-static-access-tree]').forEach(tree=>{
        tree.querySelectorAll('details').forEach(item=>item.open=false);
        const scope=tree.closest('.panel')||tree.parentElement;
        scope?.querySelector('[data-tree-expand-all]')?.addEventListener('click',()=>tree.querySelectorAll('details').forEach(item=>item.open=true));
        scope?.querySelector('[data-tree-collapse-all]')?.addEventListener('click',()=>tree.querySelectorAll('details').forEach(item=>item.open=false));
      });
    }
"""
classic = classic.replace(start_anchor, static_block + start_anchor + "\n      bindStaticTrees();", 1)

comparison = sources["comparison"].replace("details.open=depth===0;", "details.open=false;", 1)

profile = sources["profile"]
profile = profile.replace("<details open>", "<details>")
heading = "    <h2>Árvore de acessos</h2>"
new_heading = """    <div class="tree-panel-heading">
      <h2>Árvore de acessos</h2>
      <div class="tree-expand-controls">
        <button type="button" class="secondary" data-tree-expand-all>Expandir tudo</button>
        <button type="button" class="secondary" data-tree-collapse-all>Recolher tudo</button>
      </div>
    </div>
    <div class="static-access-tree" data-static-access-tree>"""
profile = profile.replace(heading, new_heading, 1)

# Fecha exatamente o conteiner inserido antes do fechamento da section da arvore.
end_marker = "    {% if ns.path_open %}</div></details>{% endif %}"
profile = profile.replace(end_marker, end_marker + "\n    </div>", 1)

css_block = """

/* ARVORES_RECOLHIVEIS_V2 */
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
styles = sources["styles"].rstrip() + css_block

updated = {
    "classic": classic,
    "comparison": comparison,
    "profile": profile,
    "styles": styles,
}

# Verificacao secundaria antes de criar backup ou gravar.
checks = {
    "classic": [MARK, "details.open=false", "data-tree-expand-all", "bindStaticTrees();"],
    "comparison": ["details.open=false", "expand-all", "collapse-all"],
    "profile": ["data-static-access-tree", "data-tree-expand-all", "data-tree-collapse-all"],
    "styles": ["ARVORES_RECOLHIVEIS_V2", ".tree-expand-controls"],
}
for name, markers in checks.items():
    absent = [marker for marker in markers if marker not in updated[name]]
    if absent:
        raise RuntimeError(
            f"Falha ao preparar {TARGETS[name]}: {', '.join(absent)}. "
            "Nenhum arquivo foi alterado."
        )

# Backup integral dos quatro arquivos.
for path in TARGETS.values():
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)

try:
    for name, path in TARGETS.items():
        path.write_text(updated[name], encoding="utf-8")

    # Confere os arquivos efetivamente gravados. Em qualquer falha, restaura tudo.
    for name, markers in checks.items():
        saved = TARGETS[name].read_text(encoding="utf-8")
        absent = [marker for marker in markers if marker not in saved]
        if absent:
            raise RuntimeError(f"Validacao final falhou em {TARGETS[name]}: {', '.join(absent)}")
except Exception:
    for path in TARGETS.values():
        backup_file = BACKUP / path.relative_to(ROOT)
        if backup_file.exists():
            shutil.copy2(backup_file, path)
    raise

print("\n[SUCESSO] Arvores recolhiveis V2 instaladas.")
print("[OK] Arvores iniciam fechadas, mostrando apenas os modulos principais.")
print("[OK] Expansao individual preservada.")
print("[OK] Botoes Expandir tudo e Recolher tudo adicionados.")
print("[OK] Consolidado, perfis do usuario, perfil individual e comparacao tratados.")
print(f"[BACKUP] {BACKUP}")
print("\nReinicie o servidor e atualize o navegador com Ctrl+F5.")
