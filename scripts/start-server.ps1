[CmdletBinding()]
param([switch]$Background)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$server = Join-Path $root 'services\xiaozhi-esp32-server\main\xiaozhi-server'
$localConfig = Join-Path $root 'config\local.server.yaml'
$env:PATH = (Join-Path $root 'tools\native') + ';' + $env:PATH
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HUB_OFFLINE = '1'
$env:TOKENIZERS_PARALLELISM = 'false'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $root '.venv-dev\Scripts\python.exe'))) { throw 'Run scripts/setup.ps1 to create the development environment.' }
if (-not (Test-Path -LiteralPath (Join-Path $server 'app.py'))) { throw 'Upstream source download is incomplete.' }
if (-not (Test-Path -LiteralPath $localConfig)) { throw 'Copy config/server.example.yaml to config/local.server.yaml and configure it.' }
& (Join-Path $root '.venv-dev\Scripts\python.exe') (Join-Path $root 'scripts\validate_config.py') $localConfig
if ($LASTEXITCODE -ne 0) { throw 'Fix the configuration errors above before starting.' }
& $python -c 'import importlib.util,sys; names=["aiohttp","websockets","torch","funasr","edge_tts","opuslib_next"]; missing=[n for n in names if importlib.util.find_spec(n) is None]; print("Missing packages: " + ", ".join(missing)) if missing else None; sys.exit(bool(missing))'
if ($LASTEXITCODE -ne 0) { throw 'Run scripts/setup.ps1 -InstallServerDependencies to install upstream requirements.' }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw 'Install FFmpeg and make ffmpeg.exe available on PATH.' }
# Importing the wrapper also checks whether a native Opus library is loadable.
& $python -c 'import opuslib_next'
if ($LASTEXITCODE -ne 0) { throw 'A native Opus library is required in addition to the opuslib_next Python package.' }
New-Item -ItemType Directory -Force -Path (Join-Path $server 'data'),(Join-Path $root 'logs\server'),(Join-Path $root 'data\server') | Out-Null
Copy-Item -LiteralPath $localConfig -Destination (Join-Path $server 'data\.config.yaml') -Force
$runtime = Join-Path $root 'data\runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$stateFile = Join-Path $runtime 'server.json'
if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)"
    if ($existing -and $existing.CommandLine -like '*scripts*run_server.py*') {
        Write-Host "Server is already running (PID $($state.pid))."
        return
    }
}
& (Join-Path $PSScriptRoot 'start-iot.ps1')
& (Join-Path $root '.venv-dev/Scripts/python.exe') (Join-Path $PSScriptRoot 'make_greeting.py')
if ($LASTEXITCODE -ne 0) { throw 'Greeting asset generation failed.' }
Remove-Item -LiteralPath (Join-Path $runtime 'stop-server') -ErrorAction SilentlyContinue
$runner = Join-Path $root 'scripts\run_server.py'
if ($Background) {
    $process = Start-Process -FilePath $python -ArgumentList @('-u', ('"' + $runner + '"')) -WorkingDirectory $server -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'logs\server\stdout.log') -RedirectStandardError (Join-Path $root 'logs\server\stderr.log')
    Write-Host "Server starting (PID $($process.Id)). Logs: logs/server/stdout.log and stderr.log"
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        if ($process.HasExited) { throw 'Server exited during startup. Inspect logs/server.' }
        try {
            $result = Invoke-WebRequest -Uri 'http://127.0.0.1:8003/xiaozhi/ota/' -TimeoutSec 1
            if ($result.StatusCode -eq 200) { Write-Host 'Server ready: OTA 8003 / WebSocket 8000'; return }
        } catch { }
        Start-Sleep -Seconds 1
    }
    throw 'Server did not become ready within 90 seconds. Inspect logs/server.'
}
Push-Location -LiteralPath $server
try { & $python -u $runner; $serverExit = $LASTEXITCODE } finally { Pop-Location }
if ($serverExit -ne 0) { throw "Upstream server stopped with exit code $serverExit. Inspect its startup output." }
