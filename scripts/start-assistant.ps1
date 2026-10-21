[CmdletBinding()]
param([switch]$ShowWeb, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'

# Reuse the existing launchers and their process ownership checks.
& (Join-Path $PSScriptRoot 'start-server.ps1') -Background
& (Join-Path $PSScriptRoot 'start-iot.ps1')

$ota = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8003/xiaozhi/ota/' -TimeoutSec 5
if ($ota.StatusCode -ne 200) { throw 'OTA service is unavailable. Inspect logs/server.' }
$socket = New-Object System.Net.Sockets.TcpClient
try {
    $pending = $socket.ConnectAsync('127.0.0.1', 8000)
    if (-not $pending.Wait(3000) -or -not $socket.Connected) { throw 'Voice WebSocket port 8000 is unavailable.' }
} finally { $socket.Dispose() }
$root = Split-Path -Parent $PSScriptRoot
$stateFile = Join-Path $root 'data/runtime/iot-state.json'
$online = $false
if (Test-Path -LiteralPath $stateFile) {
    $status = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $online = ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $status.at -lt 5) -and (@($status.devices).Count -gt 0)
}
Write-Host ('Hardware online: ' + $online)
Write-Host 'Hardware voice service ready. Assistant starts in standby.'
Write-Host 'Say the configured activation phrase on the hardware to start.'
if ($ShowWeb) {
    & (Join-Path $PSScriptRoot 'start-web.ps1')
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8006/' }
}
