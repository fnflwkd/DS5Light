param([string]$DistPath = 'dist-1.0', [string]$PythonExe = '.venv/Scripts/python.exe')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force reports | Out-Null
if (!(Test-Path -LiteralPath $PythonExe)) {
    if ($PythonExe -ne '.venv/Scripts/python.exe') { throw 'Selected Python executable not found' }
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 가상환경 생성 실패' }
}
& $PythonExe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw '의존성 설치 실패' }
$driverMetadata = Get-Content vendor/driver-components.json -Raw | ConvertFrom-Json
foreach ($component in @('vigem','hidhide')) {
    $item = $driverMetadata.$component
    $installer = Join-Path "vendor/$component" $item.filename
    if (!(Test-Path -LiteralPath $installer)) { throw "Missing build dependency: $installer. See README.md." }
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $item.sha256) { throw "Installer hash mismatch: $installer" }
}
& "$PSScriptRoot/native/build-vigem.ps1" -PythonExe $PythonExe
if ($LASTEXITCODE -ne 0) { throw 'Xbox native client build failed' }
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /platform:x64 /target:exe /out:ProcessCapture.exe '.\native\ProcessCapture.cs'
if ($LASTEXITCODE -ne 0) { throw 'Process capture helper build failed' }
& $PythonExe -m PyInstaller --noconfirm --clean --onedir --windowed --name DS5Light --distpath $DistPath --icon 'assets/dslight.ico' --add-data 'assets;assets' --add-data 'vendor;vendor' --add-binary 'ProcessCapture.exe;.' --exclude-module matplotlib --exclude-module pandas --exclude-module torch --exclude-module IPython app.py
if ($LASTEXITCODE -ne 0) { throw '빌드 실패' }
# Windows 10/11 uses the operating system UCRT; omit locally collected OS DLLs.
$ds5Internal = (Resolve-Path "$DistPath/DS5Light/_internal").Path
Get-ChildItem -LiteralPath $ds5Internal -File | Where-Object { $_.Name -eq 'ucrtbase.dll' -or $_.Name -like 'api-ms-win-*.dll' } | ForEach-Object {
    if ($_.DirectoryName -ne $ds5Internal) { throw 'Unexpected DLL location' }
    Remove-Item -LiteralPath $_.FullName
}
& $PythonExe package_notices.py --exe "$DistPath/DS5Light/DS5Light.exe" --target "$DistPath/DS5Light/THIRD_PARTY"
if ($LASTEXITCODE -ne 0) { throw '라이선스 고지 준비 실패' }
Copy-Item CHANGELOG_100.txt,LICENSE.txt,LICENSE_EN.txt,README.txt,README_KO.txt,default_config.json,SOURCES.md -Destination "$DistPath/DS5Light"

Copy-Item -Recurse -Force studio-presets -Destination "$DistPath/DS5Light"

# Remove legacy Markdown READMEs left by an older build in the same output folder.
foreach ($ds5Readme in @('README.md','README_KO.md','studio-presets/README.md','studio-presets/README_KO.md')) {
    $ds5LegacyReadme = Join-Path "$DistPath/DS5Light" $ds5Readme
    if (Test-Path -LiteralPath $ds5LegacyReadme) { Remove-Item -LiteralPath $ds5LegacyReadme }
}
