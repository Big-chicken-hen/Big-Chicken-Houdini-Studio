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
$studioPythonw = Join-Path $studioRoot '.runtime/venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $studioPythonw -PathType Leaf)) {
    throw 'Windowed Python is missing. Run setup again or use -Console.'
}
Start-Process -FilePath $studioPythonw -ArgumentList @('"' + (Join-Path $studioRoot 'scripts/launch_window.pyw') + '"') -WorkingDirectory $studioRoot -WindowStyle Hidden
