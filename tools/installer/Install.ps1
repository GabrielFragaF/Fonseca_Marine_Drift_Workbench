param([string]$InstallDirectory, [switch]$NoShortcuts)
$ErrorActionPreference = 'Stop'
try {
    $source = Join-Path $PSScriptRoot 'Marine Drift Workbench'
    if (-not (Test-Path -LiteralPath (Join-Path $source 'Marine Drift Workbench.exe'))) {
        throw 'Extract the entire ZIP first, then run Install.cmd.'
    }
    if (-not $InstallDirectory) {
        $InstallDirectory = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Marine Drift Workbench 0.1.1'
    }
    $destination = [IO.Path]::GetFullPath($InstallDirectory)
    if (Test-Path -LiteralPath $destination) {
        $answer = Read-Host "An installation already exists at '$destination'. Replace it? (Y/N)"
        if ($answer -notmatch '^[Yy]') {
            Write-Host 'Installation cancelled.'
            exit 0
        }
        Remove-Item -LiteralPath $destination -Recurse -Force
    }
    Write-Host 'Installing Marine Drift Workbench with its Python and scientific libraries...'
    New-Item -ItemType Directory -Path $destination | Out-Null
    Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $destination -Recurse
    $executable = Join-Path $destination 'Marine Drift Workbench.exe'
    if (-not $NoShortcuts) {
        $shell = New-Object -ComObject WScript.Shell
        foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
            $shortcut = $shell.CreateShortcut((Join-Path $folder 'Marine Drift Workbench.lnk'))
            $shortcut.TargetPath = $executable
            $shortcut.WorkingDirectory = [Environment]::GetFolderPath('MyDocuments')
            $shortcut.Description = 'Local marine reverse-drift modelling'
            $shortcut.Save()
        }
    }
    Write-Host "Installed successfully: $destination"
    Write-Host 'Open Marine Drift Workbench using the desktop or Start menu shortcut.'
    Write-Host 'Python does not need to be installed separately.'
} catch {
    Write-Error $_
    exit 1
}
