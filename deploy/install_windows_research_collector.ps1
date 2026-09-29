param([string]$TaskName = 'CryptoForge Research Collector')

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $Root '.venv\Scripts\pythonw.exe'
$Script = Join-Path $Root 'scripts\windows_background_runner.py'
if (-not (Test-Path -LiteralPath $Python)) { throw "Python environment is missing: $Python" }
if (-not (Test-Path -LiteralPath (Join-Path $Root '.env'))) { throw '.env is missing.' }

$Arguments = '"{0}" collector --scan-universe --selection-name research-collector --universe-limit 8' -f $Script
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Dynamic Bybit universe and market-data sync to Supabase every two minutes.' -Force | Out-Null
Write-Output "installed_task=$TaskName"
