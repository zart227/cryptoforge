param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $Root
$DataDir = Join-Path $Root 'data\live-pilot'
$LogDir = Join-Path $Root 'logs'
$LogPath = Join-Path $LogDir 'windows-github-update.log'
$StatusPath = Join-Path $DataDir 'update-status.json'
$LockPath = Join-Path $DataDir 'update.lock'
$LiveConfig = Join-Path $DataDir 'freqtrade.live.json'
$Database = Join-Path $DataDir 'tradesv3.sqlite'
$LiveSwitch = Join-Path $DataDir 'live-enabled'
$NoEntrySwitch = Join-Path $DataDir 'no-new-entry'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Freqtrade = Join-Path $Root '.venv\Scripts\freqtrade.exe'
$DbHelper = Join-Path $Root 'scripts\windows_live_db.py'
$StrategyPath = Join-Path $Root 'user_data\strategies\CryptoForgeSmallBalancePilotStrategy.py'
$LockStream = $null

function Write-UpdateStatus([string]$State, [string]$Detail = '') {
    $record = [ordered]@{
        checked_at = [DateTime]::UtcNow.ToString('o')
        state = $State
        detail = $Detail
    }
    $json = $record | ConvertTo-Json -Depth 4
    $json | Set-Content -LiteralPath $StatusPath -Encoding utf8
    Add-Content -LiteralPath $LogPath -Value ("{0} {1} {2}" -f $record.checked_at, $State, $Detail)
}

function Invoke-Git([string[]]$Arguments) {
    $output = & git -c "safe.directory=$Root" @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("git {0} failed: {1}" -f ($Arguments -join ' '), ($output -join ' '))
    }
    return ($output -join "`n").Trim()
}

function Get-LiveDbStatus {
    $output = & $Python $DbHelper status --database $Database 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Cannot read live database status: $($output -join ' ')" }
    return ($output -join "`n") | ConvertFrom-Json
}

function Get-LiveProcesses {
    $needle = 'data/live-pilot/freqtrade.live.json'
    return @(Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq 'python.exe' -or $_.Name -eq 'freqtrade.exe') -and
        $_.CommandLine -and $_.CommandLine.Contains($needle)
    })
}

function Test-LiveConfig {
    $config = Get-Content -LiteralPath $LiveConfig -Raw | ConvertFrom-Json
    if ($config.dry_run -ne $false -or $config.trading_mode -ne 'spot' -or
        $config.initial_state -ne 'running' -or $config.stake_amount -ne 5.02 -or
        $config.max_open_trades -ne 1 -or $config.stoploss -ne -0.005 -or
        @($config.exchange.pair_whitelist).Count -ne 1 -or
        $config.exchange.pair_whitelist[0] -ne 'XRP/USDT') {
        throw 'Live config no longer matches the approved Spot pilot limits.'
    }
    if ($config.exchange.key -or $config.exchange.secret) {
        throw 'Live config must obtain API credentials from process environment only.'
    }
    $source = Get-Content -LiteralPath $StrategyPath -Raw
    foreach ($required in @('confirm_trade_entry', 'max_order_notional_usdt', 'live-enabled', 'daily_realized')) {
        if (-not $source.Contains($required)) {
            throw "Pilot strategy is missing required safety gate: $required"
        }
    }
    if ($source -notmatch 'max_order_notional_usdt\s*=\s*Decimal\("5\.02"\)') {
        throw 'Pilot strategy order-notional ceiling changed; manual review is required.'
    }
}

function Import-ProjectEnvironment {
    $envFile = Join-Path $Root '.env'
    if (-not (Test-Path -LiteralPath $envFile)) { throw '.env is missing.' }
    foreach ($raw in [System.IO.File]::ReadLines($envFile)) {
        $line = $raw.Trim().TrimStart([char]0xFEFF)
        if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
        $parts = $line.Split('=', 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.Length -ge 2 -and
            (($value[0] -eq '"' -and $value[$value.Length - 1] -eq '"') -or
             ($value[0] -eq "'" -and $value[$value.Length - 1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
    $apiKey = [Environment]::GetEnvironmentVariable('BYBIT_API_KEY', 'Process')
    $apiSecret = [Environment]::GetEnvironmentVariable('BYBIT_API_SECRET', 'Process')
    if (-not $apiKey -or -not $apiSecret) { throw 'Bybit credentials are absent from .env.' }
    [Environment]::SetEnvironmentVariable('FREQTRADE__EXCHANGE__KEY', $apiKey, 'Process')
    [Environment]::SetEnvironmentVariable('FREQTRADE__EXCHANGE__SECRET', $apiSecret, 'Process')
}

function Start-LiveBot {
    Import-ProjectEnvironment
    $stdout = Join-Path $LogDir 'freqtrade-live.stdout.log'
    $stderr = Join-Path $LogDir 'freqtrade-live.stderr.log'
    $liveLog = Join-Path $LogDir 'freqtrade-live-local.log'
    $logOffset = if (Test-Path -LiteralPath $liveLog) { (Get-Item -LiteralPath $liveLog).Length } else { 0 }
    $startedAt = Get-Date
    Start-Process -FilePath $Freqtrade -ArgumentList @(
        'trade', '--config', 'data/live-pilot/freqtrade.live.json', '--userdir', 'user_data',
        '--strategy', 'CryptoForgeSmallBalancePilotStrategy', '--db-url',
        'sqlite:///./data/live-pilot/tradesv3.sqlite', '--logfile',
        'logs/freqtrade-live-local.log', '--no-color'
    ) -WorkingDirectory $Root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Seconds 3
        $processes = Get-LiveProcesses
        $recent = @()
        if (Test-Path -LiteralPath $liveLog) {
            $stream = [System.IO.File]::Open($liveLog, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
            try {
                if ($stream.Length -lt $logOffset) { $logOffset = 0 }
                [void]$stream.Seek($logOffset, [System.IO.SeekOrigin]::Begin)
                $reader = [System.IO.StreamReader]::new($stream)
                $text = $reader.ReadToEnd()
                $recent = @($text -split "`r?`n")
            } finally { $stream.Dispose() }
        }
        $running = ($recent | Where-Object { $_ -match 'Changing state to: RUNNING' }).Count -gt 0
        $wallets = ($recent | Where-Object { $_ -match 'Wallets synced\.' }).Count -gt 0
        $errors = ($recent | Where-Object { $_ -match ' - ERROR - ' }).Count -gt 0
        if ($processes.Count -gt 0 -and $running -and $wallets -and -not $errors) { return }
        if ($errors -and $processes.Count -eq 0) { throw 'Freqtrade failed to initialize; inspect logs/freqtrade-live-local.log.' }
    } while ((Get-Date) -lt $deadline)
    throw 'Timed out waiting for Freqtrade to become healthy.'
}

try {
    New-Item -ItemType Directory -Force -Path $DataDir, $LogDir | Out-Null
    $LockStream = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)

    if ((Invoke-Git @('branch', '--show-current')) -ne 'main') {
        Write-UpdateStatus 'blocked_wrong_branch' 'Expected local branch main.'
        exit 0
    }
    Invoke-Git @('fetch', '--quiet', 'origin', 'main') | Out-Null
    $head = Invoke-Git @('rev-parse', 'HEAD')
    $remote = Invoke-Git @('rev-parse', 'refs/remotes/origin/main')
    if (-not (Invoke-Git @('status', '--porcelain'))) {
        # Empty is the clean state.
    } else {
        Write-UpdateStatus 'blocked_dirty_worktree' 'Commit and push local changes before automatic updates can proceed.'
        exit 0
    }
    if ($head -eq $remote) {
        Write-UpdateStatus 'up_to_date' $head
        exit 0
    }
    & git -c "safe.directory=$Root" merge-base --is-ancestor $remote $head
    if ($LASTEXITCODE -eq 0) {
        Write-UpdateStatus 'local_ahead_of_github' 'Push the prepared local commit to GitHub before remote updates can be applied.'
        exit 0
    }
    & git -c "safe.directory=$Root" merge-base --is-ancestor $head $remote
    if ($LASTEXITCODE -ne 0) {
        Write-UpdateStatus 'blocked_diverged_history' 'Local and GitHub main have diverged.'
        exit 0
    }
    & git -c "safe.directory=$Root" diff --quiet $head $remote -- pyproject.toml poetry.lock uv.lock requirements.txt requirements-dev.txt
    if ($LASTEXITCODE -eq 1) {
        Write-UpdateStatus 'blocked_dependency_change' 'Dependency manifests changed; install and validate dependencies manually.'
        exit 0
    }
    if ($LASTEXITCODE -gt 1) { throw 'Could not compare dependency manifests.' }
    if ($CheckOnly) {
        Write-UpdateStatus 'update_available' "$head -> $remote"
        exit 0
    }

    $processes = Get-LiveProcesses
    $dbState = Get-LiveDbStatus
    if ($processes.Count -eq 0 -and ($dbState.open_trades -gt 0 -or $dbState.open_orders -gt 0)) {
        Write-UpdateStatus 'blocked_inactive_with_exposure' 'Bot is not running while the database shows an open trade/order.'
        exit 0
    }

    $resumeEntries = (Test-Path $LiveSwitch) -and -not (Test-Path $NoEntrySwitch)
    if ($processes.Count -gt 0 -and $resumeEntries -and -not (Test-Path (Join-Path $DataDir 'update-pending.json'))) {
        @{ resume_entries = $true; from = $head; to = $remote } |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $DataDir 'update-pending.json') -Encoding utf8
    }
    if ($processes.Count -gt 0) {
        Set-Content -LiteralPath $NoEntrySwitch -Value 'enabled' -Encoding ascii
        if ($dbState.open_trades -gt 0 -or $dbState.open_orders -gt 0) {
            Write-UpdateStatus 'waiting_for_flat' "open_trades=$($dbState.open_trades); open_orders=$($dbState.open_orders); new entries disabled"
            exit 0
        }
        & $Python $DbHelper backup --database $Database --backup-dir (Join-Path $DataDir 'backups') | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Live database backup failed.' }
        Remove-Item -LiteralPath $LiveSwitch -ErrorAction SilentlyContinue
        foreach ($process in $processes) {
            Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
        if ((Get-LiveProcesses).Count -gt 0) { throw 'Could not stop the old Freqtrade process.' }
    }

    Invoke-Git @('merge', '--ff-only', $remote) | Out-Null
    Test-LiveConfig
    & $Python -m compileall -q src user_data/strategies
    if ($LASTEXITCODE -ne 0) { throw 'Python compilation check failed.' }
    $strategyOutput = & $Freqtrade list-strategies --userdir user_data --no-color 2>&1
    if ($LASTEXITCODE -ne 0 -or (($strategyOutput -join "`n") -notmatch 'CryptoForgeSmallBalancePilotStrategy\s+.*OK')) {
        throw 'Freqtrade strategy discovery check failed.'
    }

    if ($processes.Count -gt 0) {
        Start-LiveBot
        $pendingPath = Join-Path $DataDir 'update-pending.json'
        $restoreEntries = $false
        if (Test-Path $pendingPath) {
            $pending = Get-Content -LiteralPath $pendingPath -Raw | ConvertFrom-Json
            $restoreEntries = [bool]$pending.resume_entries
            Remove-Item -LiteralPath $pendingPath
        }
        if ($restoreEntries) {
            Set-Content -LiteralPath $LiveSwitch -Value 'enabled' -Encoding ascii
            Remove-Item -LiteralPath $NoEntrySwitch -ErrorAction SilentlyContinue
        }
        Write-UpdateStatus 'updated_and_running' "$head -> $remote; entries_restored=$restoreEntries"
    } else {
        Write-UpdateStatus 'updated_bot_was_stopped' "$head -> $remote"
    }
} catch {
    Write-UpdateStatus 'failed_closed' $_.Exception.Message
    throw
} finally {
    if ($LockStream) { $LockStream.Dispose() }
    Remove-Item -LiteralPath $LockPath -ErrorAction SilentlyContinue
}
