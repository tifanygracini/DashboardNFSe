# Varredura mensal dos certificados digitais: percorre todas as subpastas da CERT_PASTA, coleta as senhas
# anotadas (nome do arquivo, .txt ao lado ou nome da subpasta), confere cada uma abrindo o certificado,
# guarda no Gerenciador de Credenciais a senha do certificado válido de cada empresa e gera o relatório
# logs\certificados-AAAA-MM.csv (sem senhas) com o que mudou: certificados novos, vencidos, sem senha.
#
# É este arquivo que a tarefa mensal chama (criada pelo scripts\agendar.ps1). Também pode ser rodado à mão:
#   powershell -ExecutionPolicy Bypass -File scripts\varrer-certificados.ps1

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

$exe = @("venv", ".venv") |
    ForEach-Object { Join-Path $Raiz "$_\Scripts\nfse-empresas.exe" } |
    Where-Object { Test-Path $_ } | Select-Object -First 1

$pastaLogs = Join-Path $Raiz "logs"
New-Item -ItemType Directory -Force $pastaLogs | Out-Null
$log = Join-Path $pastaLogs ("certificados-{0:yyyy-MM}.log" -f (Get-Date))
$relatorio = Join-Path $pastaLogs ("certificados-{0:yyyy-MM}.csv" -f (Get-Date))

function Escrever($texto) { Add-Content -Path $log -Value $texto -Encoding UTF8 }

Escrever ("==== início {0:yyyy-MM-dd HH:mm:ss} ({1})" -f (Get-Date), $env:USERNAME)
if (-not $exe) {
    Escrever "ERRO: não achei venv\Scripts\nfse-empresas.exe. Rode: venv\Scripts\python -m pip install -e `".[keyring]`""
    exit 2
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

cmd /c "`"$exe`" certificados --relatorio `"$relatorio`" >> `"$log`" 2>&1"
$codigo = $LASTEXITCODE
Escrever ("==== fim {0:yyyy-MM-dd HH:mm:ss}, código de saída {1}" -f (Get-Date), $codigo)
exit $codigo
