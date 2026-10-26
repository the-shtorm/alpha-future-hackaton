param([string]$EnvFile = '.env', [string]$ProjectName = '')
$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'setup-demo.ps1') -EnvFile $EnvFile
Push-Location $demoRoot
try {
    $demoArguments = @('compose', '--env-file', $EnvFile)
    if ($ProjectName) { $demoArguments += @('--project-name', $ProjectName) }
    & docker @demoArguments up --build --detach --wait --wait-timeout 2400
    $demoExit = $LASTEXITCODE
    if ($demoExit -eq 0) { Write-Output 'Demo is ready. Open http://localhost:3000 (or FRONTEND_PORT from your environment file).' }
} finally {
    Pop-Location
}
exit $demoExit
