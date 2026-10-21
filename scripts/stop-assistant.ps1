$ErrorActionPreference = 'Stop'
# Stop the response service first; the hardware cannot get another AI reply.
& (Join-Path $PSScriptRoot 'stop-server.ps1')
& (Join-Path $PSScriptRoot 'stop-web.ps1')
& (Join-Path $PSScriptRoot 'stop-iot.ps1')
Write-Host 'Local assistant services stopped. Hardware power is unchanged.'
