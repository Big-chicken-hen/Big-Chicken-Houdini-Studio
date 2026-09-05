param(
    [string]$Python = 'python',
    [switch]$BackendOnly,
    [switch]$Dev,
    [switch]$NoIndex,
    [string]$FindLinks
)
$ErrorActionPreference = 'Stop'
$studioRoot = if ($env:HIA_PROJECT_ROOT) { (Resolve-Path -LiteralPath $env:HIA_PROJECT_ROOT).Path } else { Split-Path -Parent $PSScriptRoot }
$env:HIA_PROJECT_ROOT = $studioRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
$studioArgs = @((Join-Path $studioRoot 'scripts/setup.py'))
if ($BackendOnly) { $studioArgs += '--backend-only' }
if ($Dev) { $studioArgs += '--dev' }
if ($NoIndex) { $studioArgs += '--no-index' }
if ($FindLinks) { $studioArgs += @('--find-links', $FindLinks) }
& $Python @studioArgs
exit $LASTEXITCODE
