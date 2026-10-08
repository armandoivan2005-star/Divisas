param(
    [switch]$CreateAdmin
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "No existe $envPath. Completa el archivo .env antes de continuar."
}

$values = @{}
Get-Content -LiteralPath $envPath | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $key, $value = $line.Split('=', 2)
        $values[$key.Trim()] = $value.Trim()
    }
}

$required = @(
    'DJANGO_SECRET_KEY',
    'DB_NAME',
    'DB_USER',
    'DB_PASSWORD',
    'DB_HOST',
    'DB_PORT',
    'DB_SSLMODE',
    'DB_SCHEMA'
)

foreach ($key in $required) {
    $value = $values[$key]
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match 'PASTE_|YOUR_|PROJECT_REF') {
        throw "Falta completar $key en .env."
    }
}

if ($values['DB_ENGINE'] -ne 'postgresql') {
    throw 'DB_ENGINE debe ser postgresql.'
}
if ($values['DB_SSLMODE'] -notin @('require', 'verify-ca', 'verify-full')) {
    throw 'DB_SSLMODE debe exigir SSL para Supabase.'
}
if ($values['DB_SCHEMA'] -ne 'django_app') {
    throw 'DB_SCHEMA debe ser django_app para coincidir con el SQL de preparacion.'
}
if ($values['DB_HOST'] -in @('localhost', '127.0.0.1')) {
    throw 'DB_HOST todavia apunta a una base local.'
}

$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'No existe .venv. Crea el entorno e instala requirements.txt antes de continuar.'
}

try {
    Push-Location $projectRoot

    & $python manage.py check --database default
    if ($LASTEXITCODE -ne 0) { throw 'Fallo manage.py check.' }

    & $python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Fallo manage.py migrate.' }

    & $python manage.py showmigrations
    if ($LASTEXITCODE -ne 0) { throw 'Fallo showmigrations.' }

    & $python manage.py shell -c "from django.contrib.auth.models import User, Group; from divisas.models import FavoriteCurrency, AdminNotification, ExchangeAlert, UserAlertNotification; print({'users': User.objects.count(), 'groups': Group.objects.count(), 'favorites': FavoriteCurrency.objects.count(), 'admin_notifications': AdminNotification.objects.count(), 'alerts': ExchangeAlert.objects.count(), 'alert_notifications': UserAlertNotification.objects.count()})"
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la verificacion de conteos.' }

    if ($CreateAdmin) {
        & $python manage.py createsuperuser --username armando
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el administrador.' }
    }
}
finally {
    Pop-Location
}

Write-Host 'Supabase quedo inicializado y verificado para Django.' -ForegroundColor Green
