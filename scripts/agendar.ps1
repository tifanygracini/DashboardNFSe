# Cria (ou atualiza) as Tarefas Agendadas do robô de NFS-e, com o usuário do Windows que executar este script:
#   nfse-robo-diario            dias úteis no horário escolhido (Acessórias + certificados + ADN)
#   nfse-certificados-mensal    uma vez por mês: varredura completa das subpastas de certificados, coleta das
#                               senhas anotadas e relatório logs\certificados-AAAA-MM.csv
#
# Uso (PowerShell normal, sem "Executar como administrador", na pasta do projeto):
#   powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1 -Hora 07:30 -TestarAgora
#   powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1 -DiaMensal 5 -HoraMensal 06:30
#
# Conferir:  Get-ScheduledTask -TaskName "nfse-*" | Get-ScheduledTaskInfo
# Remover:   Unregister-ScheduledTask -TaskName "nfse-robo-diario" -Confirm:$false
#            Unregister-ScheduledTask -TaskName "nfse-certificados-mensal" -Confirm:$false
#
# As tarefas rodam só com o usuário conectado ao Windows (não precisa estar na frente do computador,
# basta a sessão aberta, mesmo com a tela bloqueada). Motivos:
#   - a unidade S: (onde estão os certificados) é mapeada por usuário e não existe fora da sessão;
#   - as senhas dos certificados guardadas no Gerenciador de Credenciais (keyring) são do usuário.

param(
    [string]$Hora = "07:00",
    [string]$NomeTarefa = "nfse-robo-diario",
    [ValidateRange(1, 28)][int]$DiaMensal = 1,
    [string]$HoraMensal = "06:30",
    [string]$NomeTarefaMensal = "nfse-certificados-mensal",
    [switch]$TestarAgora
)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$rodar = Join-Path $PSScriptRoot "rodar-robo.ps1"
$varrer = Join-Path $PSScriptRoot "varrer-certificados.ps1"
$usuarioWindows = "$env:USERDOMAIN\$env:USERNAME"

$exe = @("venv", ".venv") |
    ForEach-Object { Join-Path $Raiz "$_\Scripts\nfse-baixar.exe" } |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) {
    Write-Host "Não achei venv\Scripts\nfse-baixar.exe em $Raiz." -ForegroundColor Red
    Write-Host "Rode antes: venv\Scripts\python -m pip install -e `".[keyring]`""
    exit 1
}
try {
    $inicio = [datetime]::ParseExact($Hora, "HH:mm", $null)
    $inicioMensal = [datetime]::ParseExact($HoraMensal, "HH:mm", $null)
}
catch { Write-Host "Hora inválida. Use o formato HH:mm, por exemplo 08:00." -ForegroundColor Red; exit 1 }

# ---- tarefa diária do robô
$acao = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $Raiz `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$rodar`""
$gatilho = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $inicio
$usuario = New-ScheduledTaskPrincipal -UserId $usuarioWindows -LogonType Interactive -RunLevel Limited
$config = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -MultipleInstances IgnoreNew
# StartWhenAvailable: se o computador estava desligado no horário, roda assim que a sessão abrir.
# ExecutionTimeLimit: se travar (ADN fora do ar, por exemplo), o Windows encerra depois de 4 horas (são centenas de empresas).

Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilho -Principal $usuario `
    -Settings $config -Description "Acessórias + certificados + NFS-e do ADN de todas as empresas" `
    -Force | Out-Null

Write-Host "Tarefa '$NomeTarefa' criada: dias úteis às $Hora, usuário $env:USERNAME." -ForegroundColor Green
Write-Host "Logs de cada execução: $Raiz\logs\robo-AAAA-MM-DD.log"

# ---- tarefa mensal dos certificados. Os cmdlets do PowerShell não têm gatilho mensal: usa o serviço de
#      agendamento do Windows diretamente, com as mesmas regras da tarefa diária.
$servico = New-Object -ComObject "Schedule.Service"
$servico.Connect()
$def = $servico.NewTask(0)
$def.RegistrationInfo.Description = "Varre as subpastas de certificados digitais, coleta as senhas e gera o relatório mensal"
$def.Settings.StartWhenAvailable = $true
$def.Settings.DisallowStartIfOnBatteries = $false
$def.Settings.StopIfGoingOnBatteries = $false
$def.Settings.ExecutionTimeLimit = "PT2H"
$def.Settings.MultipleInstances = 2          # se ainda estiver rodando, não abre outra
$def.Principal.LogonType = 3                 # só com o usuário conectado (unidade S: e Gerenciador de Credenciais)
$def.Principal.RunLevel = 0
$gatilhoMensal = $def.Triggers.Create(4)     # mensal
$gatilhoMensal.DaysOfMonth = [int][math]::Pow(2, $DiaMensal - 1)
$gatilhoMensal.MonthsOfYear = 4095           # todos os meses
$gatilhoMensal.StartBoundary = (Get-Date).Date.Add($inicioMensal.TimeOfDay).ToString("yyyy-MM-ddTHH:mm:ss")
$acaoMensal = $def.Actions.Create(0)
$acaoMensal.Path = "powershell.exe"
$acaoMensal.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$varrer`""
$acaoMensal.WorkingDirectory = $Raiz
$servico.GetFolder("\").RegisterTaskDefinition($NomeTarefaMensal, $def, 6, $usuarioWindows, $null, 3) | Out-Null

Write-Host "Tarefa '$NomeTarefaMensal' criada: todo dia $DiaMensal do mês às $HoraMensal." -ForegroundColor Green
Write-Host "Relatório de cada mês: $Raiz\logs\certificados-AAAA-MM.csv"

if ($TestarAgora) {
    Start-ScheduledTask -TaskName $NomeTarefa
    Write-Host "Execução de teste iniciada. Acompanhe o log de hoje na pasta logs."
}
