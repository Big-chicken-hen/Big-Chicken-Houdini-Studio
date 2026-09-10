param([string]$Output)
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
if (-not $Output) { $Output = Join-Path $studioRoot 'Studio.exe' }
$studioCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $studioCompiler -PathType Leaf)) {
    throw 'The Windows .NET Framework C# compiler is missing.'
}
$studioSource = Join-Path $studioRoot 'release\StudioLauncher.cs'
& $studioCompiler /nologo /target:winexe /platform:x64 /optimize+ ('/out:' + $Output) $studioSource
if ($LASTEXITCODE -ne 0) { throw 'Studio.exe build failed.' }
