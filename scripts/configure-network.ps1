# Run elevated to allow only the local XiaoZhi ports on the private WLAN.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$report = Join-Path $root 'data/hardware/firewall-result.json'
try {
    $python = Join-Path $root 'tools/python310/python.exe'
    $prior = @()
    foreach ($rule in (Get-NetFirewallRule -DisplayName 'Python' -ErrorAction SilentlyContinue)) {
        $filter = $rule | Get-NetFirewallApplicationFilter
        $programPath = $filter.Program -replace '[\\/]+', '\'
        if ($rule.Action -eq 'Block' -and $rule.Direction -eq 'Inbound' -and $programPath -ieq $python -and $rule.Name -like 'TCP*') {
            $prior += @{Name=$rule.Name;Profile=[string]$rule.Profile}
            Set-NetFirewallRule -Name $rule.Name -Profile Public
        }
    }
    $name = 'XiaoZhi-Local-Private-TCP'
    if (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) { Remove-NetFirewallRule -Name $name }
    New-NetFirewallRule -Name $name -DisplayName 'XiaoZhi local assistant (private WLAN)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000,8003 -Program $python -Profile Private -InterfaceAlias WLAN -RemoteAddress LocalSubnet | Out-Null
    $iotName='XiaoZhi-EchoEar-IoT'
    if (Get-NetFirewallRule -Name $iotName -ErrorAction SilentlyContinue) { Remove-NetFirewallRule -Name $iotName }
    New-NetFirewallRule -Name $iotName -DisplayName 'EchoEar authenticated IoT (device only)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 1883 -Profile Private -InterfaceAlias WLAN -RemoteAddress 192.168.16.22 | Out-Null
    @{success=$true;previousRules=$prior;ports=@(8000,8003)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $report
} catch {
    @{success=$false;error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $report
    throw
}
