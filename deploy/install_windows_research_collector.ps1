param([string]$TaskName = 'CryptoForge Research Collector')

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Script = Join-Path $Root 'scripts\sync_supabase_market_data.py'
if (-not (Test-Path -LiteralPath $Python)) { throw "Python environment is missing: $Python" }
if (-not (Test-Path -LiteralPath (Join-Path $Root '.env'))) { throw '.env is missing.' }

$Command = @"
Set-Location -LiteralPath '$Root'
Get-Content -LiteralPath '$Root\.env' | ForEach-Object {
    `$line = `$_.Trim()
    if (`$line -and -not `$line.StartsWith('#') -and `$line.Contains('=')) {
        `$parts = `$line.Split('=', 2)
        `$value = `$parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable(`$parts[0].Trim(), `$value, 'Process')
    }
}
& '$Python' '$Script' --scan-universe --selection-name research-collector --universe-limit 8
exit `$LASTEXITCODE
"@
$Encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -EncodedCommand $Encoded"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Dynamic Bybit universe and market-data sync to Supabase every two minutes.' -Force | Out-Null
Write-Output "installed_task=$TaskName"
