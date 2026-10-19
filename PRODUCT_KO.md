# DS5 Light

[English](README.md) · [설치 안내](SETUP_KO.md) · [사용설명서(TXT)](README_KO.txt)

**[DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio)용 경량 Windows 오디오햅틱 전처리기**입니다.

동글로 보내는 게임 오디오 복사본에 적응형 필터를 적용합니다. BGM·대사로 생기는 불필요한 진동을 줄이면서 효과음의 타이밍과 촉감을 살리는 것이 목표입니다. 귀로 듣는 게임 소리는 바꾸지 않습니다.

## 주요 기능

- 선택한 게임 또는 출력 장치 전체의 오디오 캡처
- 디테일·균형·억제 스타일과 억제 강도 조절
- 5.1 입력에서 후방 LR·센터·LFE 개별 선택
- 게임별 설정을 저장하는 12개 프리셋 슬롯
- 한국어·영어 UI
- Studio용 **Audio Haptics**와 **DS Native** 프로필 제공

## 필터의 핵심 원리

시간에 따른 소리 변화를 살펴 Studio 처리 전에 한 번 더 조절합니다.

1. **적응형 배경 추정:** 소리를 네 개 대역으로 나눠 최근의 에너지 수준을 기억합니다. 배경 수준에 머무르는 소리는 더 줄이고, 그보다 새롭게 커지는 소리는 상대적으로 덜 줄입니다.
2. **순간적인 변화 보호:** 갑작스러운 음량 증가를 최근 변화와 비교해 타격·총격 같은 짧은 효과가 과하게 약해지는 것을 줄입니다. 순간음이라고 필터를 완전히 우회하지는 않습니다.
3. **제한적이고 부드러운 감쇠:** 대역별 감소량에 한도를 두고 서서히 바꿉니다. 좌우에는 공통 제어값을 사용하며 자동으로 출력 볼륨을 끌어올리지는 않습니다.

기본 경로는 대형 AI 모델이나 GPU 추론을 사용하지 않는 CPU 신호 처리입니다. 악기나 목소리를 인식해 따로 분리하는 방식은 아니므로 음악의 타격음이 남거나 지속 효과음이 약해질 수도 있습니다. 게임·오디오 구성·Studio 설정에 따라 결과가 달라집니다.

## 준비물

- Windows 10/11 64비트. 선택한 게임만 캡처하려면 Windows 빌드 20348 이상이 필요하며, 이전 Windows 10에서는 장치 전체 캡처를 사용할 수 있습니다.
- DS5Dongle-Studio가 설치된 지원 동글과 DualSense
- Studio 오디오햅틱 설정. 처음에는 제공하는 Audio Haptics 프로필을 기준으로 사용하세요.

## 다운로드와 실행

이 저장소의 Releases에서 **Windows-x64 ZIP**을 받으세요. GitHub의 소스 코드 ZIP과는 다릅니다. 압축을 전부 풀고 `DS5Light.exe`를 실행하면 되며, 실행 배포본에는 Python을 따로 설치할 필요가 없습니다.

1. [설치 안내](SETUP_KO.md)에 따라 제공 프로필 두 개를 Studio에 저장합니다.
2. Studio에서 **Audio Haptics**를 활성화하고 DS5 Light를 실행합니다.
3. 게임을 선택하고 PC 억제 필터를 켠 뒤 **균형 → 시작**으로 사용합니다.
4. 네이티브 햅틱 게임을 할 때는 DS5 Light를 정지하고 Studio의 **DS Native**를 활성화합니다.

배포 기본값은 PC 필터 꺼짐입니다. 채널 선택은 게임 내부 오디오 설정의 자동 감지가 아닙니다.

[Studio 프로필 적용 안내](studio-presets/README_KO.txt) · [빌드 안내](README_KO.txt) · [구성요소 출처](SOURCES.md)

## 출처와 라이선스

DS5 Light는 [DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio)와 함께 사용하는 비공식 보조 프로그램입니다. 독립적으로 관리되며 Studio의 공식 배포판이 아닙니다. 원 프로젝트 개발자와 기여자분들께 감사드립니다.

| 프로젝트·구성요소 | 라이선스 | 사용한 부분 |
|---|---|---|
| [DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio) | MIT | `ds5audio.py` 오디오 브리지 일부 재사용. awalol·artzox의 원저작권 고지 보존 |
| [NumPy](https://numpy.org/) | BSD-3-Clause 및 포함 구성요소별 추가 고지 | 수치·배열 연산 |
| [SciPy](https://scipy.org/) | BSD-3-Clause 및 포함 구성요소별 추가 고지 | 디지털 필터와 신호 처리 |
| [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) | 포크 기여분 Apache-2.0, 기존 PyAudio·PortAudio MIT 고지 유지 | Windows 오디오 캡처·출력 |
| [Python](https://www.python.org/) | PSF 라이선스 및 포함 구성요소별 고지 | 실행 환경 |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0-or-later와 배포 예외, 구성요소별 조건 | 실행 프로그램 패키징 |
| DS5 Light 자체 코드 | [사용자 정의 무료 이용 라이선스](LICENSE.txt) | UI·처리·통합 코드. 판매·유료 통합 제한 |

주요 구성요소를 요약한 표이며 모든 포함 의존성의 목록은 아닙니다. Studio 원문 고지는 [vendor/LICENSE-Studio.txt](vendor/LICENSE-Studio.txt), 상세 출처는 [SOURCES.md](SOURCES.md), 관련 원문은 [upstream 고지](licenses/upstream)와 실행 배포본의 `THIRD_PARTY` 폴더에서 확인할 수 있습니다. 외부 구성요소의 라이선스는 그대로 유지되며, DS5 Light 자체 코드의 제한이 이를 덮어쓰지 않습니다.

배경 추정 개념은 [noisereduce](https://github.com/timsainb/noisereduce)도 참고했습니다. 해당 구현을 런타임에 복사한 것은 아니며, 코드 의존성과 구분되는 설계 참고입니다.

## 라이선스

[DS5 Light 라이선스](LICENSE.txt)에 따라 무료 사용·수정·무료 재배포를 허용합니다. 프로그램 판매 또는 유료 제품·서비스에 통합하려면 별도 허락이 필요합니다. 수익형 게임 방송·영상 제작에 도구로 사용하는 것은 허용합니다.

[영어 번역](LICENSE_EN.txt) · [배포 정책](DISTRIBUTION_POLICY_KO.md)

한국어 라이선스 원문을 기준으로 하며, OSI 승인 오픈소스 라이선스는 아닙니다. 제3자 이미지 권한을 허락하는 문서가 아니며, 현재 아이콘의 원본 출처와 재배포 권한은 미확인 상태입니다.
