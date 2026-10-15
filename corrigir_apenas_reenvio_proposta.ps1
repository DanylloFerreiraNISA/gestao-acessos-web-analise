param(
    [string]$ProjectPath = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
$ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
$Target = Join-Path $ProjectPath 'app\access_control.py'
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Backup = Join-Path $ProjectPath "backup_apenas_reenvio_$Timestamp\app\access_control.py"

Write-Host ''
Write-Host 'CORRECAO APENAS DO REENVIO DA PROPOSTA' -ForegroundColor Cyan
Write-Host "Arquivo: $Target" -ForegroundColor DarkGray
Write-Host 'Nenhum HTML, CSS, cor ou tela sera alterado.' -ForegroundColor Yellow
Write-Host ''

if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
    throw "Arquivo ativo nao encontrado: $Target"
}

$Content = Get-Content -LiteralPath $Target -Raw -Encoding UTF8
$Original = $Content

# Localiza somente a funcao da rota /enviar.
$FunctionPattern = "(?ms)(@router\.post\(['\"]\/portal\/propostas\/\{proposal_id\}\/enviar['\"]\)\s*def\s+proposal_submit\b.*?)(?=\r?\n@router\.|\z)"
$FunctionMatch = [regex]::Match($Content, $FunctionPattern)

if (-not $FunctionMatch.Success) {
    throw 'A funcao proposal_submit da rota /enviar nao foi encontrada. Nenhum arquivo foi alterado.'
}

$FunctionText = $FunctionMatch.Value

# Se a correcao ja existe, nao duplica codigo.
if ($FunctionText -match "workflow_status\s*==\s*['\"]EM_REVISAO['\"]") {
    Write-Host 'A correcao de reenvio ja esta instalada. Nenhuma alteracao foi necessaria.' -ForegroundColor Green
    exit 0
}

# Substitui exclusivamente a validacao de estado dentro de proposal_submit.
$StatePattern = "(?m)^(?<indent>\s*)if\s+proposal\.workflow_status\s+not\s+in\s+\{(?<states>[^\r\n}]*)\}\s*:\s*raise\s+HTTPException\(409,\s*['\"]Estado nao permite envio['\"]\)\s*$"
$StateMatch = [regex]::Match($FunctionText, $StatePattern)

if (-not $StateMatch.Success) {
    throw 'A validacao esperada "Estado nao permite envio" nao foi encontrada dentro de proposal_submit. Nenhum arquivo foi alterado.'
}

$Indent = $StateMatch.Groups['indent'].Value
$Replacement = @"
${Indent}# Evita erro quando o navegador repetir um envio que ja colocou a proposta em revisao.
${Indent}if proposal.workflow_status == 'EM_REVISAO':
${Indent}    return RedirectResponse(f'/portal/propostas/{proposal.id}', status_code=303)
${Indent}if proposal.workflow_status not in {'RASCUNHO', 'DEVOLVIDO', 'REJEITADO'}:
${Indent}    raise HTTPException(409, f'A proposta nao pode ser enviada no estado {proposal.workflow_status}')
"@

$UpdatedFunction = [regex]::Replace(
    $FunctionText,
    $StatePattern,
    [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $Replacement },
    1
)

$Content = $Content.Substring(0, $FunctionMatch.Index) + $UpdatedFunction + $Content.Substring($FunctionMatch.Index + $FunctionMatch.Length)

if ($Content -eq $Original) {
    throw 'A correcao nao produziu alteracao. Nenhum arquivo foi gravado.'
}

New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
Copy-Item -LiteralPath $Target -Destination $Backup -Force
Set-Content -LiteralPath $Target -Value $Content -Encoding UTF8 -NoNewline

try {
    & python -m py_compile $Target
    if ($LASTEXITCODE -ne 0) { throw 'Falha na validacao Python.' }
}
catch {
    Copy-Item -LiteralPath $Backup -Destination $Target -Force
    throw "A validacao falhou e o arquivo original foi restaurado. $($_.Exception.Message)"
}

Write-Host 'Correcao aplicada e sintaxe validada com sucesso.' -ForegroundColor Green
Write-Host "Backup: $Backup" -ForegroundColor Yellow
Write-Host ''
Write-Host 'Agora reinicie o servidor e pressione Ctrl + F5 no navegador.' -ForegroundColor Cyan
