$ErrorActionPreference = 'Stop'
$destination = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Marine Drift Workbench 0.1.1'
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Marine Drift Workbench.lnk'
$startShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Marine Drift Workbench.lnk'

Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $startShortcut -Force -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $destination) {
    Remove-Item -LiteralPath $destination -Recurse -Force
    Write-Host 'Marine Drift Workbench was uninstalled.'
} else {
    Write-Host 'No standard Marine Drift Workbench installation was found.'
}
