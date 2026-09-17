param([switch]$Console)
$ErrorActionPreference = 'Stop'
$studioRoot = if ($env:HIA_PROJECT_ROOT) { (Resolve-Path -LiteralPath $env:HIA_PROJECT_ROOT).Path } else { Split-Path -Parent $PSScriptRoot }
$env:HIA_PROJECT_ROOT = $studioRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
$studioPython = Join-Path $studioRoot '.runtime/venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $studioPython -PathType Leaf)) {
    throw 'Run Setup Studio.cmd once before starting Studio.'
}
if ($Console) {
    & $studioPython (Join-Path $studioRoot 'scripts/run.py') launcher
    exit $LASTEXITCODE
}
$studioEntry = Join-Path $studioRoot 'Studio.exe'
if (-not (Test-Path -LiteralPath $studioEntry -PathType Leaf)) {
    throw 'Studio.exe is missing. Run Setup Studio.cmd first.'
}
Start-Process -FilePath $studioEntry -WorkingDirectory $studioRoot -WindowStyle Normal
