param([string]$TaskName = 'CryptoForge Supabase Live Executor')

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $Root '.venv\Scripts\pythonw.exe'
$Script = Join-Path $Root 'scripts\windows_background_runner.py'
$EnvFile = Join-Path $Root '.env'
if (-not (Test-Path -LiteralPath $Python)) { throw "Python environment is missing: $Python" }
if (-not (Test-Path -LiteralPath $EnvFile)) { throw '.env is missing.' }

$Required = @('SUPABASE_URL', 'BYBIT_API_KEY', 'BYBIT_API_SECRET')
$Available = @{}
foreach ($raw in [IO.File]::ReadLines($EnvFile)) {
    $line = $raw.Trim().TrimStart([char]0xFEFF)
    if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
    $parts = $line.Split('=', 2)
    $Available[$parts[0].Trim()] = $parts[1].Trim()
}
if (-not ($Available.ContainsKey('SUPABASE_SERVICE_ROLE_KEY') -or $Available.ContainsKey('SUPABASE_SECRET_KEY'))) {
    throw 'SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY is missing.'
}
foreach ($name in $Required) {
    if (-not $Available.ContainsKey($name) -or -not $Available[$name]) { throw "$name is missing." }
}

$Arguments = '"{0}" executor --use-night-research --night-research-limit 12 --allow-intraday-reversion --allow-emerging-momentum --append-fallback-pairs --pair ETH/USDT --pair NEAR/USDT --pair ENA/USDT --pair HYPE/USDT --stake-amount 5 --max-open-positions 2 --max-daily-loss 2 --stop-loss-percent 0.04 --ml-mode gate --ml-threshold 0.50 --ml-max-age-hours 36 --live --timeout 25' -f $Script
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'CryptoForge guarded research-selected Spot executor with ML entry gate.' -Force | Out-Null
Write-Output "installed_task=$TaskName"
