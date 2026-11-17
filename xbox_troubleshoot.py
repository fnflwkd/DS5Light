"""Read-only diagnosis; fixes are separate and require UI consent."""
import hidhide
import watchdog_service as watchdog
from xbox_backend import probe,pending_cleanup

def diagnose():
    lines=[];driver_ok=True;hide_ok=True;hide_error=False
    try:probe();lines.append('가상 Xbox 드라이버: 연결 가능')
    except Exception as exc:driver_ok=False;lines.append('가상 Xbox 드라이버: '+str(exc))
    try:
        state=hidhide.probe();lines.append('HidHide: 연결 가능')
        if state.get('inverse'):lines.append('반전 모드가 켜져 있습니다. HidHide 설정에서 확인하세요.');hide_ok=False
    except hidhide.Missing as exc:hide_ok=False;lines.append('HidHide: '+str(exc))
    except Exception as exc:hide_ok=False;hide_error=True;lines.append('HidHide: '+str(exc))
    service=None;start_mode=None
    try:
        service_state=watchdog.state();service=service_state['State'];start_mode=service_state.get('StartMode')
        lines.append('보호 서비스: '+service)
    except Exception as exc:lines.append('보호 서비스 조회: '+str(exc))
    from xbox_remap_session import pending as remap_pending
    pending=remap_pending() or pending_cleanup() or hidhide.pending(hidhide.journal_path()) or hidhide.pending(hidhide.access_path())
    if pending:
        action='restore';lines.append('이전 DS5Light 작업의 복구가 남아 있습니다. 가상 패드·Pico 리맵·숨김 설정 복구를 시도할 수 있습니다.')
    elif not driver_ok:
        action=None;lines.append('드라이버 확인·설치에서 설치 상태를 확인하세요. 다른 변환 앱과 게임은 먼저 종료하세요.')
    elif hide_error and service=='Stopped':
        action='watchdog';lines.append('HidHide 상태 조회에 실패했습니다. 필터 상태를 보호하는 Watchdog 시작을 시도할 수 있습니다. 이 조치로 해결된다고 보장할 수 없으며, 게임 설정·진동·입력 지연을 고치는 기능은 아닙니다.')
    else:
        action=None
        if service=='Stopped':lines.append('Watchdog가 꺼져 있어도 Xbox 모드는 사용할 수 있습니다. 중지 상태만으로는 오류가 아닙니다.')
        lines.append('자동으로 고칠 수 있는 복구 항목이 없습니다. 다른 변환 앱·Steam Input, 게임 패드 설정, 장치 연결을 확인하세요.' if hide_ok else 'HidHide 오류 내용을 확인하세요. 드라이버 확인·설치 또는 Windows 재부팅이 필요할 수 있습니다.')
    return dict(service=service,start_mode=start_mode,action=action,text='\n'.join(lines))
