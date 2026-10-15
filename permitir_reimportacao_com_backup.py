from __future__ import annotations

import py_compile
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
TARGET = ROOT / "app" / "access_control.py"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_ROOT = ROOT / f"backup_permitir_reimportacao_{STAMP}"
BACKUP = BACKUP_ROOT / "app" / "access_control.py"
MARK = "REIMPORTACAO_PERMITIDA_V1"

if not TARGET.is_file():
    raise RuntimeError(f"Arquivo nao encontrado: {TARGET}")

source = TARGET.read_text(encoding="utf-8-sig")
if MARK in source:
    print("[OK] A reimportacao ja esta habilitada.")
    raise SystemExit(0)

route_marker = "@router.post('/portal/importacoes/confirmar', response_class=HTMLResponse)"
route_start = source.find(route_marker)
if route_start < 0:
    raise RuntimeError("A rota de confirmacao nao foi encontrada. Nenhum arquivo foi alterado.")

route_source = source[route_start:]

# Remove somente a trava que bloqueia um conjunto ja concluido.
previous_pattern = re.compile(
    r"\n\s*previous\s*=\s*session\.scalar\(select\(ImportacaoPlanilha\)\.where\("
    r"ImportacaoPlanilha\.hash_arquivo\s*==\s*token,\s*"
    r"ImportacaoPlanilha\.status\s*==\s*'CONCLUIDA'\)\)\s*"
    r"\n\s*if\s+previous:\s*"
    r"\n\s*raise\s+ValueError\('Este conjunto de arquivos ja foi importado com sucesso\.'\)",
    re.MULTILINE,
)
route_source, removed = previous_pattern.subn("", route_source, count=1)
if removed != 1:
    raise RuntimeError(
        "A trava de arquivo ja importado nao foi reconhecida. Nenhum arquivo foi alterado."
    )

# Cada execucao ganha um hash de historico proprio. O token de conteudo continua
# sendo usado para localizar os dois arquivos temporarios da previa.
job_anchor = "        job = ImportacaoPlanilha(arquivo=' + '.join(filenames), hash_arquivo=token, tipo='XLSX_DUPLO', status='PROCESSANDO', criado_por_id=user.id)"
job_replacement = """        # REIMPORTACAO_PERMITIDA_V1
        execution_hash = hashlib.sha256(
            f\"{token}:{datetime.now(timezone.utc).isoformat()}:{secrets.token_hex(8)}\".encode()
        ).hexdigest()
        job = ImportacaoPlanilha(
            arquivo=' + '.join(filenames),
            hash_arquivo=execution_hash,
            tipo='XLSX_DUPLO',
            status='PROCESSANDO',
            criado_por_id=user.id,
        )"""
if job_anchor not in route_source:
    raise RuntimeError(
        "A criacao do historico da importacao nao foi reconhecida. Nenhum arquivo foi alterado."
    )
route_source = route_source.replace(job_anchor, job_replacement, 1)

# Registra no resultado qual conjunto de arquivos foi usado, sem alterar o schema.
result_anchor = "        job.status = 'CONCLUIDA'\n        job.resultado_json = json.dumps(result, ensure_ascii=False)"
result_replacement = """        result['hash_conjunto_importado'] = token
        result['reimportacao'] = True
        job.status = 'CONCLUIDA'
        job.resultado_json = json.dumps(result, ensure_ascii=False)"""
if result_anchor not in route_source:
    raise RuntimeError(
        "O fechamento da importacao nao foi reconhecido. Nenhum arquivo foi alterado."
    )
route_source = route_source.replace(result_anchor, result_replacement, 1)

updated = source[:route_start] + route_source

# Validacao antes de backup/gravar.
with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as temp:
    temp.write(updated)
    temp_name = temp.name
try:
    py_compile.compile(temp_name, doraise=True)
finally:
    Path(temp_name).unlink(missing_ok=True)

for expected in (MARK, "execution_hash", "reimportacao", "hash_conjunto_importado"):
    if expected not in updated:
        raise RuntimeError(f"Validacao falhou: {expected}. Nenhum arquivo foi alterado.")

BACKUP.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TARGET, BACKUP)

try:
    TARGET.write_text(updated, encoding="utf-8")
    py_compile.compile(str(TARGET), doraise=True)
except Exception:
    shutil.copy2(BACKUP, TARGET)
    raise

print("\n[SUCESSO] Reimportacao habilitada.")
print("[OK] O mesmo conjunto de planilhas pode ser analisado e confirmado novamente.")
print("[OK] Cada execucao recebe um registro proprio no historico.")
print("[OK] A importacao continua usando uma unica transacao e rollback em caso de erro.")
print(f"[BACKUP] {BACKUP_ROOT}")
print("\nReinicie o servidor e envie novamente as duas planilhas pela tela.")
