param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (Test-Path (Join-Path $ProjectRoot '.build-tools')) {
    $env:PYTHONPATH = (Join-Path $ProjectRoot '.build-tools') + ';' + (Join-Path $ProjectRoot 'src')
}
& $PythonCommand -m PyInstaller --noconfirm "tools/marine_drift.spec"

if ($LASTEXITCODE -ne 0) {
    throw "Windows bundle build failed (exit code $LASTEXITCODE)."
}

Write-Host "Bundle created in dist\\Marine Drift Workbench"
