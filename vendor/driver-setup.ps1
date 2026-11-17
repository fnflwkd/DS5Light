param([ValidateSet('vigem','hidhide')][string]$Component, [string]$Installer, [ValidateSet('install','repair','uninstall','disable_updater','check_update')][string]$Action='install', [Parameter(Mandatory=$true)][string]$LogPath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Report([string]$Text) { [Console]::WriteLine($Text); [Console]::Out.Flush(); if ($Action -in @('disable_updater','check_update')) { Add-Content -LiteralPath $LogPath -Value $Text -Encoding UTF8 } }
function Get-HidHideProducts {
    Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -eq 'HidHide' -and $_.Publisher -eq 'Nefarius Software Solutions e.U.' -and $_.WindowsInstaller -eq 1 -and $_.PSChildName -match '^\{[0-9A-Fa-f-]{36}\}$' }
}
try {
    $spec = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'driver-components.json') -Raw | ConvertFrom-Json).$Component
    if ($Action -in @('install','repair')) {
    Report 'Checking publisher signature...'
    $file = Get-Item -LiteralPath $Installer
    if ($file.Length -ne $spec.size -or (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne $spec.sha256) { throw 'Hash mismatch' }
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=Nefarius Software Solutions e\.U\.') { throw 'Publisher signature invalid' }
    Report 'Publisher signature verified.'
    $executable = $file.FullName
    $arguments = @('/qn','/norestart','/L*V!',('"' + $LogPath + '"'))
    if ($Component -eq 'hidhide') { $arguments = @('/exenoui') + $arguments }
    if ($Action -eq 'repair') {
        if ($Component -ne 'hidhide') { throw 'Repair is only for HidHide' }
        $entries = @(Get-HidHideProducts)
        if ($entries.Count -gt 1) { throw 'Multiple HidHide products found. Use Windows Installed apps.' }
        if ($entries.Count -eq 1) {
            $version = [string]$entries[0].DisplayVersion
            if ($version -eq $spec.version -or $version -eq ($spec.version + '.0')) {
                $executable = Join-Path $env:SystemRoot 'System32/msiexec.exe'
                $arguments = @('/famus',$entries[0].PSChildName,'/qn','/norestart','/L*V!',('"' + $LogPath + '"'))
                Report 'Repairing registered HidHide files and registry entries...'
            } elseif ([version]$version -gt [version]$spec.version) {
                throw 'A newer HidHide version is installed. Repair it using Windows Installed apps.'
            }
        }
    }
    } elseif ($Action -in @('disable_updater','check_update')) {
        if ($Component -ne 'hidhide') { throw 'Updater action is only for HidHide' }
        $base = Join-Path $env:ProgramFiles 'Nefarius Software Solutions\HidHide'
        $candidates = @((Join-Path $base 'nefarius_HidHide_Updater.exe'),(Join-Path $base 'x64\nefarius_HidHide_Updater.exe'))
        $found = @($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
        if ($found.Count -ne 1) { throw 'Cannot uniquely locate official HidHide updater. No changes made.' }
        $executable = $found[0]
        $signature = Get-AuthenticodeSignature -LiteralPath $executable
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=Nefarius Software Solutions e\.U\.') { throw 'Updater publisher signature invalid' }
        if ($Action -eq 'check_update') {
            Report 'Opening official updater for a user-requested check. Waiting for its window and child installers to close.'
            $process = Start-Process -FilePath $executable -ArgumentList '--skip-self-update' -Verb RunAs -WindowStyle Normal -Wait -PassThru
            exit $process.ExitCode
        }
        $boundedHelper = Join-Path $PSScriptRoot 'disable-updater-bounded.ps1'
        if (!(Test-Path -LiteralPath $boundedHelper -PathType Leaf)) { throw 'Missing bounded updater helper' }
        $arguments = @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"' + $boundedHelper + '"'),'-UpdaterPath',('"' + $executable + '"'))
        $executable = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
        Report 'Removing HidHide updater automatic registration. Watchdog and driver are preserved.'
    } else {
        $product = $spec.product
        if ($Component -eq 'hidhide') {
        # Read the registered MSI product; never guess a GUID across releases.
        $entries = @(Get-HidHideProducts)
        if ($entries.Count -eq 0) { Report 'HidHide MSI is not installed.'; exit 1605 }
        if ($entries.Count -ne 1) { throw 'Multiple HidHide products found. Use Windows Installed apps.' }
        $product = $entries[0].PSChildName
        }
        $executable = Join-Path $env:SystemRoot 'System32/msiexec.exe'
        $arguments = @('/x',$product,'/qn','/norestart','/L*V!',('"' + $LogPath + '"'))
    }
    Report 'Waiting for Windows administrator approval (UAC)...'
    $process = Start-Process -FilePath $executable -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -PassThru
    $processHandle = $process.Handle
    Report "Windows $Action process started. Waiting for completion..."
    $lastTail = ''; $ticks = 0
    do {
        $done = $process.WaitForExit(500)
        if ($Action -notin @('disable_updater','check_update') -and (Test-Path -LiteralPath $LogPath)) {
            try {
                $tail = (Get-Content -LiteralPath $LogPath -Tail 8 -ErrorAction Stop) -join "`n"
                if ($tail -and $tail -ne $lastTail) { Report $tail; $lastTail = $tail }
            } catch { } # Installer may briefly lock its log; retry next tick.
        }
        $ticks++
        if (!$done -and $ticks % 10 -eq 0) { Report "Windows $Action still running; waiting for completion..." }
    } until ($done)
    $process.WaitForExit()
    Report "Windows $Action returned $($process.ExitCode)."
    exit $process.ExitCode
} catch {
    Report $_.Exception.Message
    if ($_.Exception.NativeErrorCode -eq 1223) { exit 1223 }
    exit 1
}
