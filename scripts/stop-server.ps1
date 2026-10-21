$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root 'data\runtime'
$stateFile = Join-Path $runtime 'server.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Host 'Server is not running.'; return }
$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)"
if (-not $process) { Write-Host 'Server is already stopped.'; return }
if ($process.CommandLine -notlike '*scripts*run_server.py*' -or $state.runner -ne (Join-Path $root 'scripts\run_server.py')) { throw 'PID ownership check failed; refusing to stop another process.' }
Set-Content -LiteralPath (Join-Path $runtime 'stop-server') -Value 'stop'
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if (-not (Get-Process -Id $state.pid -ErrorAction SilentlyContinue)) { Write-Host 'Server stopped.'; return }
    Start-Sleep -Seconds 1
}
throw 'Graceful stop is still pending. Inspect logs/server before taking further action.'
