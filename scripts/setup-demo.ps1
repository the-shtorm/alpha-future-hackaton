param([string]$EnvFile = '.env')
$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
$demoPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $demoRoot $EnvFile }
$demoTemplate = [IO.File]::ReadAllLines((Join-Path $demoRoot '.env.example'))
$demoLines = [Collections.Generic.List[string]]::new()
if (Test-Path -LiteralPath $demoPath) {
    $demoLines.AddRange([IO.File]::ReadAllLines($demoPath))
} else {
    $demoLines.AddRange($demoTemplate)
}
foreach ($demoLine in $demoTemplate) {
    if ($demoLine -notmatch '^([A-Z][A-Z0-9_]*)=') { continue }
    $demoKey = $Matches[1]
    if (-not ($demoLines | Where-Object { $_.StartsWith($demoKey + '=') })) {
        $demoLines.Add($demoLine)
    }
}
$demoSecretKeys = @('POSTGRES_ADMIN_PASSWORD', 'DB_MIGRATOR_PASSWORD', 'DB_APP_PASSWORD',
    'PGADMIN_DEFAULT_PASSWORD', 'DEMO_PASSWORD', 'DEMO_BANK_PASSWORD', 'RECSYS_API_KEY')
foreach ($demoKey in $demoSecretKeys) {
    $demoIndexes = @(for ($demoIndex = 0; $demoIndex -lt $demoLines.Count; $demoIndex++) {
        if ($demoLines[$demoIndex].StartsWith($demoKey + '=')) { $demoIndex }
    })
    if ($demoIndexes.Count -ne 1) { throw "Expected exactly one $demoKey in the environment file." }
    $demoIndex = $demoIndexes[0]
    $demoValue = $demoLines[$demoIndex].Substring($demoKey.Length + 1).Trim().Trim('"').Trim("'")
    if ($demoValue -and -not ($demoKey -eq 'RECSYS_API_KEY' -and $demoValue -eq 'REPLACE_WITH_RANDOM_SECRET')) {
        continue
    }
    $demoBytes = New-Object byte[] 24
    $demoRng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $demoRng.GetBytes($demoBytes) } finally { $demoRng.Dispose() }
    $demoLines[$demoIndex] = $demoKey + '=' + [BitConverter]::ToString($demoBytes).Replace('-', '').ToLowerInvariant()
}
$demoParent = Split-Path -Parent $demoPath
if (-not (Test-Path -LiteralPath $demoParent)) { New-Item -ItemType Directory -Path $demoParent -Force | Out-Null }
$demoUtf8 = New-Object Text.UTF8Encoding($false)
$demoText = ($demoLines -join "`n") + "`n"
if (-not (Test-Path -LiteralPath $demoPath) -or [IO.File]::ReadAllText($demoPath) -cne $demoText) {
    [IO.File]::WriteAllText($demoPath, $demoText, $demoUtf8)
}
Write-Output 'Demo environment is ready. Account passwords are in DEMO_PASSWORD and DEMO_BANK_PASSWORD.'
