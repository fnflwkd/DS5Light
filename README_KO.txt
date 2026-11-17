# DS5 Light 1.0

Pico 2 W의 DS5Dongle-Studio와 함께 사용하는 Windows x64 오디오햅틱·버튼 리매핑 프로그램입니다.

## 실행
Releases의 Windows ZIP 전체를 풀고 DS5Light.exe를 실행하세요. _internal 폴더가 필요합니다. Python 설치는 필요하지 않습니다.
기본/Xbox 모두 입력 테스트는 오디오햅틱 OFF에서 사용합니다. 일반 진동과 오디오햅틱 동시 사용은 Studio Mix 설정을 확인하세요.
다른 패드 변환 앱은 종료한 뒤 번갈아 사용하세요. Watchdog는 Xbox와 자동 연동하지 않습니다. 드라이버 설치·제거는 사용자 동의 후 진행합니다.
설정은 %LOCALAPPDATA%/DS5Light에 저장됩니다. 장치별 복구 기록을 다른 PC로 옮기지 마세요.

## 소스 빌드
Windows x64, Python 3.12 x64(Tcl/Tk 포함), .NET Framework 4 x64 C# 컴파일러가 필요합니다.
1. `py -3.12 -m venv .venv`
2. `.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt`
3. `native/vigem-client/BUILD.txt`에 따라 Zig 0.13.0을 준비합니다. 기본 경로는 `work/native_toolchain/zig-windows-x86_64-0.13.0/zig.exe`입니다.
4. 공식 릴리스에서 아래 설치 파일을 다운로드해 지정 위치에 놓습니다. `vendor/driver-components.json`의 SHA256과 일치해야 합니다. 이 단계는 설치 파일 준비이며 드라이버 설치가 아닙니다.
   - https://github.com/nefarius/ViGEmBus/releases/tag/v1.22.0 → `vendor/vigem/ViGEmBus_1.22.0_x64_x86_arm64.exe`
   - https://github.com/nefarius/HidHide/releases/tag/v1.5.230.0 → `vendor/hidhide/HidHide_1.5.230_x64.exe`
5. `.\build.ps1 -PythonExe .\.venv\Scripts\python.exe -DistPath dist-1.0`
결과는 `dist-1.0/DS5Light`입니다. 소스 공개본에는 개발 실험·검증용 테스트 및 보고서를 포함하지 않았습니다. 공개용 build.ps1은 배포 빌드를 수행하며 전체 테스트가 실행됐다고 표시하지 않습니다.

## 사용 범위
PortAudio blocking 출력과 Studio 펌웨어를 유지합니다. 터보·토글은 지원되는 Xbox 패드 출력 전용입니다.
실제 장치·게임의 지연/CPU/품질/저장 지속성은 사용 환경에서 별도 확인이 필요합니다.

## 라이선스
LICENSE.txt 및 LICENSE_EN.txt를 확인하세요. 제3자 구성요소는 각 원래 라이선스가 적용되며 licenses/와 vendor/에 고지를 보존합니다. 변경 내역은 CHANGELOG_100.txt에 있습니다.
