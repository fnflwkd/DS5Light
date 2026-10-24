$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force reports | Out-Null
if (!(Test-Path '.venv/Scripts/python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 가상환경 생성 실패' }
}
& '.venv/Scripts/python.exe' -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw '의존성 설치 실패' }
& '.venv/Scripts/python.exe' -m unittest test_core test_compat test_process_policy test_presets test_channel_mix test_center test_localization test_studio_slots test_studio_ui test_battery test_session_settings test_resume_ui -v
if ($LASTEXITCODE -ne 0) { throw '테스트 실패' }
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /platform:x64 /target:exe /out:ProcessCapture.exe '.\native\ProcessCapture.cs'
if ($LASTEXITCODE -ne 0) { throw 'Process capture helper build failed' }
& '.venv/Scripts/python.exe' -m PyInstaller --noconfirm --clean --onedir --windowed --name DS5Light --distpath dist-0.9.8 --icon 'assets/dslight.ico' --add-data 'assets;assets' --add-data 'vendor;vendor' --add-binary 'ProcessCapture.exe;.' --exclude-module matplotlib --exclude-module pandas --exclude-module torch --exclude-module IPython app.py
if ($LASTEXITCODE -ne 0) { throw '빌드 실패' }
# Windows 10/11 uses the operating system UCRT; omit locally collected OS DLLs.
$ds5Internal = (Resolve-Path 'dist-0.9.8/DS5Light/_internal').Path
Get-ChildItem -LiteralPath $ds5Internal -File | Where-Object { $_.Name -eq 'ucrtbase.dll' -or $_.Name -like 'api-ms-win-*.dll' } | ForEach-Object {
    if ($_.DirectoryName -ne $ds5Internal) { throw 'Unexpected DLL location' }
    Remove-Item -LiteralPath $_.FullName
}
& '.venv/Scripts/python.exe' package_notices.py --exe dist-0.9.8/DS5Light/DS5Light.exe --target dist-0.9.8/DS5Light/THIRD_PARTY
if ($LASTEXITCODE -ne 0) { throw '라이선스 고지 준비 실패' }
Copy-Item LICENSE.txt,LICENSE_EN.txt,README.txt,SETUP.md,SETUP_KO.md,DISTRIBUTION_POLICY_KO.md,default_config.json,README_KO.txt,SOURCES.md -Destination dist-0.9.8/DS5Light

Copy-Item -Recurse -Force studio-presets -Destination dist-0.9.8/DS5Light

# Remove legacy Markdown READMEs left by an older build in the same output folder.
foreach ($ds5Readme in @('README.md','README_KO.md','studio-presets/README.md','studio-presets/README_KO.md')) {
    $ds5LegacyReadme = Join-Path 'dist-0.9.8/DS5Light' $ds5Readme
    if (Test-Path -LiteralPath $ds5LegacyReadme) { Remove-Item -LiteralPath $ds5LegacyReadme }
}
