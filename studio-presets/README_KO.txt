Studio 프리셋 선택

English (README.txt)

| 파일 | 포털에서 사용할 기능 | 적용 범위 |
| Audio-Haptics.profile.json | Import Profile | DS5 Light 오디오햅틱용 단일 구성. 원하는 슬롯에 저장 |
| DS-Native.profile.json | Import Profile | 제공자의 네이티브용 단일 구성. 원하는 슬롯에 저장 |

개발 초기에 첨부된 백업이 아닌, 작업 폴더에 별도로 제공된 후속 ds5dongle-slots.json을 기준으로 생성했습니다. 이번에 장치에서 새로 읽은 파일은 아닙니다. Audio Haptics의 Intensity는 100, Smoothness 30, Gate 25, LPF 80Hz, Split 50Hz/100/40, Slope 24, Haptics Gain 약 1.3이며 Speaker Volume/Gain은 0입니다. 이 수치는 해당 백업의 값이고, 모든 장치에 최적인 권장값이라는 뜻은 아닙니다. 설정은 임의로 바꾸지 않았습니다.

먼저 백업
본인 Studio 포털에서 Back up all slots로 기존 설정을 보관하세요. 필요하면 현재 활성 구성도 Export Profile로 따로 보관하세요. DS Native는 제공자의 네이티브용 프리셋이며, 받는 사람의 원래 설정을 자동 복원하는 파일이 아닙니다.

단일 프로필 두 개 사용 (추천)
1. DS5 Light가 실행 중이면 정지하고 Studio 포털에 연결합니다.
2. Import Profile에서 원하는 .profile.json을 선택합니다. 매크로 선택 질문이 나오면 의도에 맞게 선택하세요. 두 제공 프로필의 원본은 매크로를 모두 비활성화합니다.
3. 설정을 확인하고 Save to Device를 누릅니다.
4. Slots에서 본인이 지정한 슬롯에 저장하고 이름을 붙입니다. 다른 슬롯에 다른 프로필도 같은 순서로 저장하면, 다음부터 슬롯 활성화만으로 전환할 수 있습니다.
5. Audio Haptics를 활성화한 뒤 DS5 Light를 시작합니다. DS Native로 전환해 게임 본래의 네이티브 햅틱을 사용할 때는 DS5 Light도 정지하세요. PC 필터만 끄는 것은 오디오 전송 정지가 아닙니다.

단일 파일은 오디오 항목만이 아니라 해당 프로필의 트리거·장치·자이로 등 전체 설정을 포함합니다. 현재 두 프로필의 커스텀 트리거 상태 수는 0이라 미사용 저장 영역의 데이터는 단일 파일에서 제외했습니다. 일반 트리거 설정값은 모두 보존했습니다. 다른 커스텀 효과 포함 파일은 Import 단계에서 효과가 바로 기록될 수 있습니다.

확인 범위
단일 프로필 두 개의 설정값을 원본과 대조했습니다. 로컬 포털의 Import Profile 코드 형식을 확인했으나 실제 장치에 가져오기·저장·진동 시험은 하지 않았습니다. 펌웨어/포털 버전에 따라 항목 차이가 있을 수 있습니다. 출처 해시는 PROVENANCE.json에 기록했습니다.
