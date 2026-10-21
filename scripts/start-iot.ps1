$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $root 'scripts/run_iot.py'
$state = Join-Path $root 'data/runtime/iot-process.json'
if (Test-Path $state) {
    $prior = Get-Content $state | ConvertFrom-Json
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($prior.pid)"
    $listener=Get-NetTCPConnection -State Listen -LocalPort 1883 -ErrorAction SilentlyContinue
    if ($existing -and $existing.CommandLine -like '*run_iot.py*' -and $listener.OwningProcess -contains $prior.pid) { Write-Host 'IoT broker already running.'; return }
    if ($existing -and $existing.CommandLine -like '*run_iot.py*') { throw 'Existing IoT broker has no listener; inspect logs/iot before restarting.' }
    Remove-Item -LiteralPath $state
}
New-Item -ItemType Directory -Force (Join-Path $root 'logs/iot'),(Join-Path $root 'data/runtime') | Out-Null
Remove-Item -LiteralPath (Join-Path $root 'data/runtime/stop-iot') -ErrorAction SilentlyContinue
$env:PYTHONUTF8='1'
$instanceId=[guid]::NewGuid().ToString('N')
$process = Start-Process -FilePath (Join-Path $root '.venv-dev/Scripts/python.exe') -ArgumentList @('-u',('"'+$runner+'"'),$instanceId) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'logs/iot/stdout.log') -RedirectStandardError (Join-Path $root 'logs/iot/stderr.log')
for ($attempt=0; $attempt -lt 20; $attempt++) {
    if ($process.HasExited) { throw 'IoT broker failed. Inspect logs/iot.' }
    if (Test-Path $state) {
        try {
            $ready=Get-Content $state | ConvertFrom-Json
            $listener=Get-NetTCPConnection -State Listen -LocalPort 1883 -ErrorAction SilentlyContinue
            if ($ready.instance_id -eq $instanceId -and $listener.OwningProcess -contains $ready.pid) { Write-Host 'IoT broker ready.'; return }
        } catch { }
    }
    Start-Sleep -Seconds 1
}
throw 'IoT broker startup timed out.'
