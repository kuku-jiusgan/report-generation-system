$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$NodeDir = Join-Path $ProjectRoot ".tools\node"
$Npm = Join-Path $NodeDir "npm.cmd"

if (-not (Test-Path $Python) -or -not (Test-Path $Npm)) {
    & (Join-Path $ProjectRoot "scripts\setup.ps1")
}

$env:PATH = "$NodeDir;$env:PATH"
$backendArgs = "-m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010 --app-dir `"$(Join-Path $ProjectRoot 'backend')`""
Start-Process -FilePath $Python -ArgumentList $backendArgs -WorkingDirectory $ProjectRoot -WindowStyle Hidden
Start-Process -FilePath $Npm -ArgumentList "run dev" -WorkingDirectory (Join-Path $ProjectRoot "frontend") -WindowStyle Hidden
Write-Host "Development servers started." -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "API docs: http://127.0.0.1:8010/docs"
