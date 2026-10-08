param(
    [string]$Bind = '127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "No existe $envPath."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'No existe .venv. Instala primero las dependencias del proyecto.'
}

try {
    Push-Location $projectRoot
    # Local development only: DEBUG remains disabled, so --insecure lets
    # Django serve the compiled static assets without changing production.
    & $python manage.py runserver --insecure $Bind
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
