# Executa o robô de todas as empresas e grava tudo que ele escreve em logs\robo-AAAA-MM-DD.log:
#   1. nfse-empresas sincronizar   cadastro das empresas ativas do Acessórias
#   2. nfse-empresas certificados  certificados A1 da pasta de rede (CERT_PASTA)
#   3. nfse-baixar                 ADN de cada empresa com certificado + importação das notas novas
# Se 1 ou 2 falharem (Acessórias fora do ar, unidade de rede desconectada), o 3 roda com o cadastro que
# já está no banco; o erro fica no log.
#
# É este arquivo que a Tarefa Agendada chama. Também pode ser rodado à mão para testar:
#   powershell -ExecutionPolicy Bypass -File scripts\rodar-robo.ps1

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

$scripts = @("venv", ".venv") |
    ForEach-Object { Join-Path $Raiz "$_\Scripts" } |
    Where-Object { Test-Path (Join-Path $_ "nfse-baixar.exe") } | Select-Object -First 1

$pastaLogs = Join-Path $Raiz "logs"
New-Item -ItemType Directory -Force $pastaLogs | Out-Null
$log = Join-Path $pastaLogs ("robo-{0:yyyy-MM-dd}.log" -f (Get-Date))

function Escrever($texto) { Add-Content -Path $log -Value $texto -Encoding UTF8 }

Escrever ("==== início {0:yyyy-MM-dd HH:mm:ss} ({1})" -f (Get-Date), $env:USERNAME)
if (-not $scripts) {
    Escrever "ERRO: não achei venv\Scripts\nfse-baixar.exe. Rode: venv\Scripts\python -m pip install -e `".[keyring]`""
    exit 2
}

# acentos corretos no log, sem depender da página de código do Windows
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Rodar([string]$exe, [string]$argumentos = "") {
    Escrever ("---- {0:HH:mm:ss} {1} {2}" -f (Get-Date), $exe, $argumentos)
    cmd /c "`"$scripts\$exe`" $argumentos >> `"$log`" 2>&1"
    return $LASTEXITCODE
}

Rodar "nfse-empresas.exe" "sincronizar" | Out-Null
Rodar "nfse-empresas.exe" "certificados" | Out-Null
$codigo = Rodar "nfse-baixar.exe"
Escrever ("==== fim {0:yyyy-MM-dd HH:mm:ss}, código de saída {1}" -f (Get-Date), $codigo)

# guarda só os últimos 90 dias de logs
Get-ChildItem $pastaLogs -Filter "robo-*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-90) } | Remove-Item -ErrorAction SilentlyContinue

exit $codigo
