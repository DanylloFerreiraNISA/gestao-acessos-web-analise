param(
    [string]$ProjectPath = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
$ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
$Target = Join-Path $ProjectPath 'app\access_control.py'
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupDir = Join-Path $ProjectPath "backup_apenas_reenvio_$Timestamp\app"
$BackupFile = Join-Path $BackupDir 'access_control.py'

Write-Host ''
Write-Host 'CORRECAO APENAS DO REENVIO DA PROPOSTA' -ForegroundColor Cyan
Write-Host "Arquivo: $Target" -ForegroundColor DarkGray
Write-Host 'Nenhum HTML, CSS, cor, template ou tela sera alterado.' -ForegroundColor Yellow
Write-Host ''

if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
    throw "Arquivo ativo nao encontrado: $Target"
}

$Content = Get-Content -LiteralPath $Target -Raw -Encoding UTF8
$Original = $Content

# Se a correcao ja estiver presente, nao duplica o codigo.
$AlreadyFixedSingle = "if proposal.workflow_status == 'EM_REVISAO':"
$AlreadyFixedDouble = 'if proposal.workflow_status == "EM_REVISAO":'

if ($Content.Contains($AlreadyFixedSingle) -or $Content.Contains($AlreadyFixedDouble)) {
    Write-Host 'A correcao de reenvio ja esta presente. Nenhum arquivo foi alterado.' -ForegroundColor Green
    exit 0
}

# Procura apenas a linha antiga da validacao do envio.
$OldLineSingle = "    if proposal.workflow_status not in {'RASCUNHO', 'DEVOLVIDO', 'REJEITADO'}: raise HTTPException(409, 'Estado nao permite envio')"
$OldLineWithoutRejected = "    if proposal.workflow_status not in {'RASCUNHO', 'DEVOLVIDO'}: raise HTTPException(409, 'Estado nao permite envio')"

$NewBlock = @'
    # Se o navegador repetir o envio depois de colocar a proposta em revisao,
    # apenas retorna para os detalhes sem gerar erro ou duplicar o historico.
    if proposal.workflow_status == 'EM_REVISAO':
        return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)
    if proposal.workflow_status not in {'RASCUNHO', 'DEVOLVIDO', 'REJEITADO'}:
        raise HTTPException(409, f'A proposta nao pode ser enviada no estado {proposal.workflow_status}')
'@

if ($Content.Contains($OldLineSingle)) {
    $Content = $Content.Replace($OldLineSingle, $NewBlock.TrimEnd("`r", "`n"))
}
elseif ($Content.Contains($OldLineWithoutRejected)) {
    $Content = $Content.Replace($OldLineWithoutRejected, $NewBlock.TrimEnd("`r", "`n"))
}
else {
    throw 'A linha antiga "Estado nao permite envio" nao foi encontrada no formato esperado. Nenhum arquivo foi alterado.'
}

if ($Content -eq $Original) {
    throw 'Nenhuma alteracao foi produzida. O arquivo permaneceu intacto.'
}

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
Copy-Item -LiteralPath $Target -Destination $BackupFile -Force
Set-Content -LiteralPath $Target -Value $Content -Encoding UTF8 -NoNewline

try {
    & python -m py_compile $Target
    if ($LASTEXITCODE -ne 0) {
        throw 'Falha na validacao de sintaxe do Python.'
    }
}
catch {
    Copy-Item -LiteralPath $BackupFile -Destination $Target -Force
    throw "A validacao falhou. O access_control.py original foi restaurado automaticamente. Detalhe: $($_.Exception.Message)"
}

Write-Host 'Correcao aplicada e validada com sucesso.' -ForegroundColor Green
Write-Host "Backup criado em: $BackupFile" -ForegroundColor Yellow
Write-Host ''
Write-Host 'Reinicie o servidor e pressione Ctrl + F5 no navegador.' -ForegroundColor Cyan
