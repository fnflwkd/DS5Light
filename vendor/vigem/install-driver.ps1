param([string]$Installer,[ValidateSet('install','uninstall','disable_updater')][string]$Action='install',[Parameter(Mandatory=$true)][string]$LogPath)
& (Join-Path $PSScriptRoot '../driver-setup.ps1') -Component 'vigem' -Installer $Installer -Action $Action -LogPath $LogPath
exit $LASTEXITCODE
