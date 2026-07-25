param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Frontend = Join-Path $ProjectRoot "frontend\dist\index.html"

if (-not (Test-Path $Python) -or -not (Test-Path $Frontend)) {
    Write-Host "The application has not been set up yet. Running setup..." -ForegroundColor Yellow
    & (Join-Path $ProjectRoot "scripts\setup.ps1")
}

$env:PYTHONPATH = Join-Path $ProjectRoot "backend"
$OnlyOfficeConfig = "C:\Program Files\ONLYOFFICE\DocumentServer\config\local.json"
if (Test-Path $OnlyOfficeConfig) {
    $OnlyOfficeSettings = Get-Content -LiteralPath $OnlyOfficeConfig -Raw | ConvertFrom-Json
    $env:REPORT_ONLYOFFICE_JWT_SECRET = [string]$OnlyOfficeSettings.services.CoAuthoring.secret.browser.string
}
Write-Host "Report Studio is starting..." -ForegroundColor Cyan
Write-Host "Open http://$HostAddress`:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
& $Python -m uvicorn app.main:app --host $HostAddress --port $Port --app-dir (Join-Path $ProjectRoot "backend")
