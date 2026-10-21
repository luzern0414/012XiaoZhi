[CmdletBinding()]
param([switch]$InstallServerDependencies)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$devPython = Join-Path $root '.venv-dev\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $devPython)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv venv --python 3.12 (Join-Path $root '.venv-dev')
    } else {
        & py -3.12 -m venv (Join-Path $root '.venv-dev')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create the Python 3.12 development environment.' }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv pip install --python $devPython --requirement (Join-Path $root 'requirements-dev.txt')
} else {
    & $devPython -m pip install --requirement (Join-Path $root 'requirements-dev.txt')
}
if ($LASTEXITCODE -ne 0) { throw 'Development dependencies could not be installed.' }
$localConfig = Join-Path $root 'config\local.server.yaml'
if (-not (Test-Path -LiteralPath $localConfig)) {
    Copy-Item -LiteralPath (Join-Path $root 'config\server.example.yaml') -Destination $localConfig
}
$asrSource = Join-Path $root 'services\xiaozhi-esp32-server\main\xiaozhi-server\models\SenseVoiceSmall'
$asrDestination = Join-Path $root 'data\models\SenseVoiceSmall'
if (Test-Path -LiteralPath $asrSource) {
    New-Item -ItemType Directory -Force -Path $asrDestination | Out-Null
    Get-ChildItem -LiteralPath $asrSource -File | ForEach-Object {
        $target = Join-Path $asrDestination $_.Name
        if (-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $_.FullName -Destination $target }
    }
}
if ($InstallServerDependencies) {
  $bundledPython = Join-Path $root 'tools\python310\python.exe'
  if (-not (Test-Path -LiteralPath $bundledPython)) {
    & $devPython (Join-Path $root 'scripts\install_assets.py') --python-only
    if ($LASTEXITCODE -ne 0) { throw 'Python installer download failed.' }
    $installer = Join-Path $root 'tools\installers\python-3.10.11-amd64.exe'
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*') { throw 'Python installer publisher verification failed.' }
    $pythonTarget = Join-Path $root 'tools\python310'
    $arguments = '/quiet InstallAllUsers=0 TargetDir="' + $pythonTarget + '" Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=0 PrependPath=0 AssociateFiles=0 Shortcuts=0'
    $installation = Start-Process -FilePath $installer -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($installation.ExitCode -notin @(0,3010) -or -not (Test-Path -LiteralPath $bundledPython)) { throw 'Python 3.10 installation failed.' }
  }
  if (-not (Test-Path -LiteralPath $python)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv venv --python $bundledPython (Join-Path $root '.venv')
    } else {
        & $bundledPython -m venv (Join-Path $root '.venv')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create the Python 3.10 environment. Install Python 3.10 or uv.' }
  }
    & $devPython (Join-Path $root 'scripts\install_assets.py')
    if ($LASTEXITCODE -ne 0) { throw 'Audio libraries or ASR model installation failed.' }
    & $devPython (Join-Path $root 'scripts\install_assets.py') --torch-only
    if ($LASTEXITCODE -ne 0) { throw 'PyTorch wheel verification failed.' }
    $torchWheel = Join-Path $root 'tools\installers\torch-2.2.2-cp310-cp310-win_amd64.whl'
    $requirements = Join-Path $root 'config\requirements-server.lock.txt'
    if (-not (Test-Path -LiteralPath $requirements)) { throw 'The upstream server checkout is incomplete.' }
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv pip install --python $python --requirement $requirements $torchWheel --link-mode=copy
    } else {
        & $python -m pip install --requirement $requirements $torchWheel
    }
    if ($LASTEXITCODE -ne 0) { throw 'Upstream dependencies could not be installed.' }
}
Write-Host 'Environment ready. Configuration: config/local.server.yaml'
Write-Host 'Start: scripts/start-server.ps1 -Background; scripts/start-web.ps1'
