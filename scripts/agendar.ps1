# Cria (ou atualiza) a Tarefa Agendada do robô de NFS-e: roda todo dia no horário escolhido,
# com o usuário do Windows que executar este script.
#
# Uso (PowerShell normal, sem "Executar como administrador", na pasta do projeto):
#   powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1 -Hora 07:30 -TestarAgora
#
# Conferir:  Get-ScheduledTask -TaskName "nfse-robo-diario" | Get-ScheduledTaskInfo
# Remover:   Unregister-ScheduledTask -TaskName "nfse-robo-diario" -Confirm:$false
#
# A tarefa roda só com o usuário conectado ao Windows (não precisa estar na frente do computador,
# basta a sessão aberta, mesmo com a tela bloqueada). Motivos:
#   - a unidade S: (onde está o certificado) é mapeada por usuário e não existe fora da sessão;
#   - a senha do certificado guardada no Gerenciador de Credenciais (keyring) é do usuário.

param(
    [string]$Hora = "07:00",
    [string]$NomeTarefa = "nfse-robo-diario",
    [switch]$TestarAgora
)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$rodar = Join-Path $PSScriptRoot "rodar_robo.ps1"

$exe = @("venv", ".venv") |
    ForEach-Object { Join-Path $Raiz "$_\Scripts\nfse-baixar.exe" } |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) {
    Write-Host "Não achei venv\Scripts\nfse-baixar.exe em $Raiz." -ForegroundColor Red
    Write-Host "Rode antes: venv\Scripts\python -m pip install -e ."
    exit 1
}
try { $inicio = [datetime]::ParseExact($Hora, "HH:mm", $null) }
catch { Write-Host "Hora inválida: '$Hora'. Use o formato HH:mm, por exemplo 08:00." -ForegroundColor Red; exit 1 }

$acao = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Raiz `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$rodar`""
$gatilho = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $inicio
$usuario = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$config = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew
# StartWhenAvailable: se o computador estava desligado no horário, roda assim que a sessão abrir.
# ExecutionTimeLimit: se travar (ADN fora do ar, por exemplo), o Windows encerra depois de 1 hora.

Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilho -Principal $usuario `
    -Settings $config -Description "Baixa as NFS-e do ADN e envia as notas para o banco (nfse-baixar)" `
    -Force | Out-Null

Write-Host "Tarefa '$NomeTarefa' criada: todos os dias às $Hora, usuário $env:USERNAME." -ForegroundColor Green
Write-Host "Logs de cada execução: $Raiz\logs\robo-AAAA-MM-DD.log"

if ($TestarAgora) {
    Start-ScheduledTask -TaskName $NomeTarefa
    Write-Host "Execução de teste iniciada. Acompanhe o log de hoje na pasta logs."
}
