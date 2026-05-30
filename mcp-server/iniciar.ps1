# Arranca el servidor MCP en esta PC leyendo la config de .env (junto a server.py).
#   pwsh -File mcp-server\iniciar.ps1
# Para dejarlo siempre encendido, registra esto en el Programador de tareas de
# Windows (Task Scheduler) con disparador "Al iniciar sesion".
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir
if (-not (Test-Path ".env")) {
  Write-Warning "No hay .env. Copia .env.example a .env y define al menos UTHAGENTES_TOKEN."
}
Write-Host "Iniciando servidor MCP uthAgentes desde $dir ..."
python server.py
