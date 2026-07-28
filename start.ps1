param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Frontend = Join-Path $ProjectRoot "frontend\dist\index.html"
$Database = Join-Path $ProjectRoot "data\report-system.db"

if (-not (Test-Path $Python) -or -not (Test-Path $Frontend)) {
    Write-Host "The application has not been set up yet. Running setup..." -ForegroundColor Yellow
    & (Join-Path $ProjectRoot "scripts\setup.ps1")
}

$HasUsers = & $Python -c "import sqlite3,pathlib; p=pathlib.Path(r'$Database'); c=sqlite3.connect(p) if p.exists() else None; print(int(bool(c) and bool(c.execute(\"SELECT 1 FROM sqlite_master WHERE type='table' AND name='auth_users'\").fetchone()) and c.execute('SELECT COUNT(*) FROM auth_users').fetchone()[0] > 0))"
if ($HasUsers -eq "0") {
    if (-not $env:REPORT_BOOTSTRAP_ADMIN_USERNAME) {
        $env:REPORT_BOOTSTRAP_ADMIN_USERNAME = Read-Host "Initial administrator username (default: admin)"
        if (-not $env:REPORT_BOOTSTRAP_ADMIN_USERNAME) { $env:REPORT_BOOTSTRAP_ADMIN_USERNAME = "admin" }
    }
    if (-not $env:REPORT_BOOTSTRAP_ADMIN_PASSWORD) {
        $SecurePassword = Read-Host "Initial administrator password (at least 8 characters)" -AsSecureString
        $PasswordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
        try { $env:REPORT_BOOTSTRAP_ADMIN_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($PasswordPointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($PasswordPointer) }
    }
}

$env:PYTHONPATH = Join-Path $ProjectRoot "backend"
$OnlyOfficeConfig = "C:\Program Files\ONLYOFFICE\DocumentServer\config\local.json"
if (Test-Path $OnlyOfficeConfig) {
    $OnlyOfficeSettings = Get-Content -LiteralPath $OnlyOfficeConfig -Raw | ConvertFrom-Json
    $env:REPORT_ONLYOFFICE_JWT_SECRET = [string]$OnlyOfficeSettings.services.CoAuthoring.secret.browser.string
}
Write-Host "Report Studio is starting..." -ForegroundColor Cyan
Write-Host "Open http://$HostAddress`:$Port" -ForegroundColor Green
Write-Host "Administration http://$HostAddress`:$Port/admin/" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
& $Python -m uvicorn app.main:app --host $HostAddress --port $Port --app-dir (Join-Path $ProjectRoot "backend")
