param(
    [switch]$SkipRuntimeDownload
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $ProjectRoot ".tools"
$PythonDir = Join-Path $ToolsDir "python"
$NodeDir = Join-Path $ToolsDir "node"
$CacheDir = Join-Path $ToolsDir "downloads"

New-Item -ItemType Directory -Force -Path $ToolsDir, $CacheDir | Out-Null

function Get-ProjectPython {
    $candidate = Join-Path $PythonDir "python.exe"
    if (Test-Path $candidate) { return $candidate }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*WindowsApps*") { return $command.Source }
    return $null
}

function Get-ProjectNode {
    $candidate = Join-Path $NodeDir "node.exe"
    if (Test-Path $candidate) { return $candidate }
    $command = Get-Command node -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}

if (-not $SkipRuntimeDownload) {
    if (-not (Get-ProjectPython)) {
        Write-Host "[1/5] Downloading Python 3.12..." -ForegroundColor Cyan
        $pythonVersion = "3.12.10"
        $pythonInstaller = Join-Path $CacheDir "python-$pythonVersion-amd64.exe"
        if (-not (Test-Path $pythonInstaller)) {
            & curl.exe --fail --location --retry 3 --output $pythonInstaller "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-amd64.exe"
            if ($LASTEXITCODE -ne 0) { throw "Python download failed." }
        }
        $arguments = "/quiet InstallAllUsers=0 TargetDir=`"$PythonDir`" Include_pip=1 Include_launcher=0 PrependPath=0 Shortcuts=0"
        $process = Start-Process -FilePath $pythonInstaller -ArgumentList $arguments -Wait -PassThru
        if ($process.ExitCode -ne 0 -or -not (Test-Path (Join-Path $PythonDir "python.exe"))) {
            throw "Python installation failed with exit code $($process.ExitCode)."
        }
    }

    if (-not (Get-ProjectNode)) {
        Write-Host "[2/5] Downloading Node.js LTS..." -ForegroundColor Cyan
        $nodeIndex = Join-Path $CacheDir "node-index.json"
        & curl.exe --fail --location --retry 3 --output $nodeIndex "https://nodejs.org/dist/index.json"
        if ($LASTEXITCODE -ne 0) { throw "Node.js release index download failed." }
        $releases = Get-Content -LiteralPath $nodeIndex -Raw | ConvertFrom-Json
        $release = $releases | Where-Object { $_.lts -and $_.files -contains "win-x64-zip" } | Select-Object -First 1
        if (-not $release) { throw "Could not find a Windows Node.js LTS release." }
        $nodeVersion = $release.version
        $nodeArchive = Join-Path $CacheDir "node-$nodeVersion-win-x64.zip"
        if (-not (Test-Path $nodeArchive)) {
            & curl.exe --fail --location --retry 3 --output $nodeArchive "https://nodejs.org/dist/$nodeVersion/node-$nodeVersion-win-x64.zip"
            if ($LASTEXITCODE -ne 0) { throw "Node.js download failed." }
        }
        $expandedDir = Join-Path $CacheDir "node-$nodeVersion"
        if (Test-Path $expandedDir) { Remove-Item -LiteralPath $expandedDir -Recurse -Force }
        Expand-Archive -LiteralPath $nodeArchive -DestinationPath $expandedDir -Force
        $extracted = Get-ChildItem -LiteralPath $expandedDir -Directory | Select-Object -First 1
        if (-not $extracted) { throw "Node.js archive was empty." }
        if (Test-Path $NodeDir) { Remove-Item -LiteralPath $NodeDir -Recurse -Force }
        Move-Item -LiteralPath $extracted.FullName -Destination $NodeDir
    }
}

$Python = Get-ProjectPython
$Node = Get-ProjectNode
if (-not $Python) { throw "Python was not found. Run this script without -SkipRuntimeDownload." }
if (-not $Node) { throw "Node.js was not found. Run this script without -SkipRuntimeDownload." }
$Npm = Join-Path (Split-Path $Node -Parent) "npm.cmd"

Write-Host "[3/5] Creating Python virtual environment..." -ForegroundColor Cyan
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    & $Python -m venv (Join-Path $ProjectRoot ".venv")
}
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "backend\requirements.txt")

Write-Host "[4/5] Installing frontend dependencies..." -ForegroundColor Cyan
$env:PATH = "$(Split-Path $Node -Parent);$env:PATH"
Push-Location (Join-Path $ProjectRoot "frontend")
try {
    & $Npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
    Write-Host "[5/5] Building Vue application..." -ForegroundColor Cyan
    & $Npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
} finally {
    Pop-Location
}

Write-Host "Setup complete. Run .\start.ps1 to open the application." -ForegroundColor Green
