$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$stateFile=Join-Path $root 'data/runtime/iot-process.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Host 'IoT broker is not running.'; return }
$state=Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
$process=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)"
if (-not $process) { Write-Host 'IoT broker is already stopped.'; return }
$runner=Join-Path $root 'scripts\run_iot.py'
if ($state.runner -ne $runner -or $process.CommandLine -notlike ('*"'+$runner+'"*') -or
    -not $state.instance_id -or $process.CommandLine -notlike ('*'+$state.instance_id+'*')) {
    throw 'IoT PID ownership check failed.'
}
$created=$process.CreationDate
Set-Content -LiteralPath (Join-Path $root 'data/runtime/stop-iot') -Value stop
for ($attempt=0; $attempt -lt 15; $attempt++) {
    if (-not (Get-Process -Id $state.pid -ErrorAction SilentlyContinue)) { Write-Host 'IoT broker stopped.'; return }
    Start-Sleep -Seconds 1
}
# Some broker tasks can remain alive after the listening socket has closed.
# Recheck identity immediately before terminating only this owned instance.
$remaining=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)"
if ($remaining) {
    if ($remaining.CreationDate -ne $created -or $remaining.CommandLine -ne $process.CommandLine) {
        throw 'IoT process identity changed; refusing to terminate a reused PID.'
    }
    Stop-Process -Id $state.pid -Force
    Wait-Process -Id $state.pid -Timeout 5 -ErrorAction SilentlyContinue
    if (Get-Process -Id $state.pid -ErrorAction SilentlyContinue) { throw 'IoT broker termination failed.' }
    Write-Host 'IoT broker stopped after graceful shutdown timed out.'
}
foreach ($name in @('iot-process.json','iot-state.json')) {
    Remove-Item -LiteralPath (Join-Path $root ('data/runtime/'+$name)) -ErrorAction SilentlyContinue
}
