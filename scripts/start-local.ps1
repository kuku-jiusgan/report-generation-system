$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root "work\runtime"
$javaHome = (Get-ChildItem (Join-Path $runtime "jdk") -Directory | Select-Object -First 1).FullName
$mavenHome = (Get-ChildItem (Join-Path $runtime "maven") -Directory | Select-Object -First 1).FullName
$python = "C:\Users\ZBYY\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$pnpm = "C:\Users\ZBYY\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
$nodeBin = "C:\Users\ZBYY\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin"
$pydeps = Join-Path $root "work\pydeps"

function Assert-PortFree([int]$port) {
  if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $port is already in use. Run scripts\stop-local.ps1 or inspect the listener."
  }
}

Assert-PortFree 5173
Assert-PortFree 8001
Assert-PortFree 8080

$jar = Join-Path $root "backend\target\report-core-0.1.0.jar"
if (-not (Test-Path $jar)) {
  $env:JAVA_HOME = $javaHome
  $env:PATH = (Join-Path $javaHome "bin") + ";" + (Join-Path $mavenHome "bin") + ";" + $env:PATH
  & (Join-Path $mavenHome "bin\mvn.cmd") -q -f (Join-Path $root "backend\pom.xml") -DskipTests package
}

$env:PYTHONPATH = $pydeps + ";" + (Join-Path $root "document-service")
$env:STORAGE_ROOT = Join-Path $root "work\local-data"
$doc = Start-Process -FilePath $python -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8001" -WorkingDirectory (Join-Path $root "document-service") -WindowStyle Hidden -PassThru

$env:DOCUMENT_SERVICE_URL = "http://127.0.0.1:8001"
$env:DEMO_MODE = "true"
$api = Start-Process -FilePath (Join-Path $javaHome "bin\java.exe") -ArgumentList "-jar",$jar -WorkingDirectory (Join-Path $root "backend") -WindowStyle Hidden -PassThru

$env:PATH = $nodeBin + ";" + $env:PATH
$web = Start-Process -FilePath $pnpm -ArgumentList "dev","--host","127.0.0.1" -WorkingDirectory (Join-Path $root "frontend") -WindowStyle Hidden -PassThru

@{documentService=$doc.Id;backend=$api.Id;frontendLauncher=$web.Id;startedAt=(Get-Date).ToString("o")} |
  ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root "work\local.pids.json") -Encoding UTF8

Write-Host "Starting local services..."
$deadline = (Get-Date).AddSeconds(30)
do {
  $ready = (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) -and
           (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) -and
           (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue)
  if ($ready) { break }
  Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

if (-not $ready) { throw "Services did not become ready within 30 seconds." }
Write-Host "System started: http://127.0.0.1:5173"
Start-Process "http://127.0.0.1:5173"
