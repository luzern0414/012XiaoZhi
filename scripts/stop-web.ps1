$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$stopFile = Join-Path $root 'data\runtime\stop-web'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stopFile) | Out-Null
Set-Content -LiteralPath $stopFile -Value 'stop'
Write-Host 'Browser tester shutdown requested.'
