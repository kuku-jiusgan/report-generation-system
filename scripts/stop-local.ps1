$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root "work\local.pids.json"

if (Test-Path $pidFile) {
  $saved = Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json
  @($saved.documentService, $saved.backend, $saved.frontendLauncher) | ForEach-Object {
    if ($_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue)) {
      Stop-Process -Id $_ -Force
    }
  }
  Remove-Item -LiteralPath $pidFile -Force
}

# pnpm may launch Vite as a child process. Stop only the project ports.
foreach ($port in 5173, 8001, 8080) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}
Write-Host "Local project services stopped."
