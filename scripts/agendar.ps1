# Registra a Tarefa Agendada "nfse-adn-diario": roda o robô do ADN todo dia às 08:00,
# usando o Python do ambiente virtual do projeto (.venv).
#
# Uso (PowerShell, na raiz do projeto):
#   .\scripts\agendar.ps1
#
# Conferir:  Get-ScheduledTask -TaskName "nfse-adn-diario" | Get-ScheduledTaskInfo
# Remover:   Unregister-ScheduledTask -TaskName "nfse-adn-diario" -Confirm:$false
#
# SENHA DO CERTIFICADO: a tarefa roda sem ninguém na frente do computador, então a senha precisa
# estar disponível sem digitação. Opções, da mais segura para a menos segura:
#   1. Gerenciador de Credenciais do Windows (recomendado):
#        .venv\Scripts\pip install keyring
#        .venv\Scripts\keyring set nfse-dashboard <CNPJ>
#      Funciona quando a tarefa roda com o mesmo usuário do Windows que guardou a senha.
#   2. CERT_SENHA no .env: quem puder ler o .env consegue usar o certificado (decisão do dono da empresa).
# Sem nenhuma das duas, o robô termina com erro claro em vez de ficar parado esperando a senha.

$ErrorActionPreference = "Stop"
$NomeTarefa = "nfse-adn-diario"
$Raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $Raiz ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Ambiente virtual não encontrado em $Raiz\.venv. Crie com: python -m venv .venv ; .venv\Scripts\pip install -e ."
    exit 1
}

$acao = New-ScheduledTaskAction -Execute $python -Argument "-m nfse.cli.baixar" -WorkingDirectory $Raiz
$gatilho = New-ScheduledTaskTrigger -Daily -At "08:00"
# StartWhenAvailable = "executar assim que possível se perdeu o horário"
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilho -Settings $config `
    -Description "Baixa as NFS-e do ADN todos os dias e atualiza o banco de notas" -Force | Out-Null

Write-Host "Tarefa '$NomeTarefa' criada: todos os dias às 08:00, na pasta $Raiz"
Write-Host "Conferir:  Get-ScheduledTask -TaskName '$NomeTarefa' | Get-ScheduledTaskInfo"
Write-Host "Remover:   Unregister-ScheduledTask -TaskName '$NomeTarefa' -Confirm:`$false"
