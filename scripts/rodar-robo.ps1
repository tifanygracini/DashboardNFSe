# Executa o robô (nfse-baixar) e grava tudo que ele escreve em logs\robo-AAAA-MM-DD.log.
# É este arquivo que a Tarefa Agendada chama. Também pode ser rodado à mão para testar:
#   powershell -ExecutionPolicy Bypass -File scripts\rodar_robo.ps1

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

$exe = @("venv", ".venv") |
    ForEach-Object { Join-Path $Raiz "$_\Scripts\nfse-baixar.exe" } |
    Where-Object { Test-Path $_ } | Select-Object -First 1

$pastaLogs = Join-Path $Raiz "logs"
New-Item -ItemType Directory -Force $pastaLogs | Out-Null
$log = Join-Path $pastaLogs ("robo-{0:yyyy-MM-dd}.log" -f (Get-Date))

function Escrever($texto) { Add-Content -Path $log -Value $texto -Encoding UTF8 }

Escrever ("==== início {0:yyyy-MM-dd HH:mm:ss} ({1})" -f (Get-Date), $env:USERNAME)
if (-not $exe) {
    Escrever "ERRO: não achei venv\Scripts\nfse-baixar.exe. Rode: venv\Scripts\python -m pip install -e ."
    exit 2
}

# acentos corretos no log, sem depender da página de código do Windows
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

cmd /c "`"$exe`" >> `"$log`" 2>&1"
$codigo = $LASTEXITCODE
Escrever ("==== fim {0:yyyy-MM-dd HH:mm:ss}, código de saída {1}" -f (Get-Date), $codigo)

# guarda só os últimos 90 dias de logs
Get-ChildItem $pastaLogs -Filter "robo-*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-90) } | Remove-Item -ErrorAction SilentlyContinue

exit $codigo
