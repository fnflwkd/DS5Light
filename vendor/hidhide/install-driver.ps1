param([string]$Installer,[ValidateSet('install','repair','uninstall','disable_updater','check_update')][string]$Action='install',[Parameter(Mandatory=$true)][string]$LogPath)
& (Join-Path $PSScriptRoot '../driver-setup.ps1') -Component 'hidhide' -Installer $Installer -Action $Action -LogPath $LogPath
exit $LASTEXITCODE
