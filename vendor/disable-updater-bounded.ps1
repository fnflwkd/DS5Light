param([Parameter(Mandatory=$true)][string]$UpdaterPath)
$ErrorActionPreference = 'Stop'
try {
    if ([IO.Path]::GetFileName($UpdaterPath) -ne 'nefarius_HidHide_Updater.exe') { throw 'Unexpected updater' }
    $signature = Get-AuthenticodeSignature -LiteralPath $UpdaterPath
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=Nefarius Software Solutions e\.U\.') { throw 'Updater publisher signature invalid' }
    # Elevated parent owns only this registration-removal process; never an installer.
    $child = Start-Process -FilePath $UpdaterPath -ArgumentList @('--uninstall','--override-success-code','0') -WindowStyle Hidden -PassThru
    $handle = $child.Handle
    if (!$child.WaitForExit(60000)) {
        $child.Kill()
        if (!$child.WaitForExit(5000)) { exit 1461 }
        exit 1460
    }
    $child.WaitForExit()
    exit $child.ExitCode
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1461
}
