param(
    [switch]$Build,
    [switch]$Logs
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.docker.example" ".env"
    Write-Host "Created .env from .env.docker.example. Fill secrets in .env, then run this script again."
    exit 2
}

$envText = Get-Content ".env" -Raw
$required = @(
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY"
)

$missing = @()
foreach ($name in $required) {
    if ($envText -notmatch "(?m)^$name=.+") {
        $missing += $name
    }
}

if ($missing.Count -gt 0) {
    Write-Host "Missing required values in .env: $($missing -join ', ')"
    Write-Host "Fill .env locally. Do not commit it."
    exit 2
}

$composeArgs = @("compose", "up", "-d")
if ($Build) {
    $composeArgs += "--build"
}

& docker @composeArgs

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& docker compose ps

if ($Logs) {
    & docker compose logs -f --tail 100
}
