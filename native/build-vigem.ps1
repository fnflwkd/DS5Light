param([string]$ZigExe = '', [string]$PythonExe = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (!$ZigExe) { $ZigExe = Join-Path $root 'work/native_toolchain/zig-windows-x86_64-0.13.0/zig.exe' }
if (!$PythonExe) { $PythonExe = Join-Path $root '.venv/Scripts/python.exe' }
if (!(Test-Path -LiteralPath $ZigExe)) { throw 'Zig 0.13.0 build tool required. See native/vigem-client/BUILD.txt. No driver installation is needed.' }
$version = & $ZigExe version
if ($version -ne '0.13.0') { throw 'Expected pinned Zig 0.13.0 compiler' }
Push-Location $root
try {
    $buildDir = Join-Path $root 'work/native_toolchain'
    New-Item -ItemType Directory -Force $buildDir | Out-Null
    $common = @('c++','-shared','-O2','-g0','-std=c++17','-DSTRSAFE_NO_DEPRECATE','-DVIGEM_DYNAMIC','-DVIGEM_EXPORTS','-DUNICODE','-D_UNICODE','-I','native/vigem-client/include','native/vigem-client/src/ViGEmClient.cpp','-lsetupapi')
    & $ZigExe @common -o (Join-Path $buildDir 'DS5LightViGEmClient.dll')
    if ($LASTEXITCODE -ne 0) { throw 'ViGEm client build failed' }
    Copy-Item -LiteralPath (Join-Path $buildDir 'DS5LightViGEmClient.dll') -Destination 'vendor/vigem/DS5LightViGEmClient.dll'
    & $PythonExe native/package-vigem.py --zig-root (Split-Path $ZigExe -Parent)
    if ($LASTEXITCODE -ne 0) { throw 'ViGEm source/notice manifest failed' }
} finally { Pop-Location }
