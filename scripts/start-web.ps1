$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $root 'scripts\run_frontend.py'
$existing = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like ('*"' + $runner + '"*') }
if ($existing) { Write-Host 'Browser tester is already running: http://127.0.0.1:8006'; return }
New-Item -ItemType Directory -Force -Path (Join-Path $root 'data\runtime'),(Join-Path $root 'logs\web') | Out-Null
Remove-Item -LiteralPath (Join-Path $root 'data\runtime\stop-web') -ErrorAction SilentlyContinue
$env:PYTHONUTF8 = '1'
$process = Start-Process -FilePath (Join-Path $root '.venv\Scripts\python.exe') -ArgumentList @('-u', ('"' + $runner + '"')) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'logs\web\stdout.log') -RedirectStandardError (Join-Path $root 'logs\web\stderr.log')
Write-Host "Browser tester starting (PID $($process.Id)): http://127.0.0.1:8006"
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ($process.HasExited) { throw 'Browser tester exited during startup. Inspect logs/web.' }
    try {
        $result = Invoke-WebRequest -Uri 'http://127.0.0.1:8006/health' -TimeoutSec 1
        if ($result.StatusCode -eq 200) { Write-Host 'Browser tester ready.'; return }
    } catch { }
    Start-Sleep -Seconds 1
}
throw 'Browser tester did not become ready. Inspect logs/web.'
