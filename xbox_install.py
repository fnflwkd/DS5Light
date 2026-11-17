"""Bundled official driver. Installation requires explicit UI consent."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import shutil
import uuid
import json

URL='https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBus_1.22.0_x64_x86_arm64.exe'
try:COMPONENTS=json.loads((Path(__file__).resolve().parent/'vendor/driver-components.json').read_text(encoding='utf8'))
except (OSError,ValueError):COMPONENTS={}
SHA256=COMPONENTS.get('vigem',{}).get('sha256','')
SIZE=COMPONENTS.get('vigem',{}).get('size',0)
BUNDLE=Path(__file__).resolve().parent/'vendor/vigem'
INSTALLER=COMPONENTS.get('vigem',{}).get('filename','ViGEmBus.exe')

def installation_notice(component):
    spec=COMPONENTS.get(component)
    if not spec:return '드라이버 정보 파일이 없습니다. ZIP 전체를 다시 풀어 주세요.'
    purpose=('중복 입력을 막기 위해 HidHide를 설치합니다. Watchdog는 함께 설치되는 드라이버 상태 점검 서비스입니다. 설치 후 업데이터 자동 실행을 해제하며, 업데이트 확인은 버튼을 누를 때만 합니다.'
             if component=='hidhide' else '가상 Xbox 패드를 만들기 위해 ViGEmBus를 설치합니다. 지원 종료된 드라이버입니다.')
    return (purpose+'\n\n드라이버 설치와 서비스 제어에는 Windows 관리자 승인(UAC)이 필요하며 재부팅이 필요할 수 있습니다.'
            +'\n\n버전: '+spec['version']+'\n공식 소스: '+spec['source']+'\n공식 배포: '+spec['release']
            +'\n\n설치 전 게시자 서명(Nefarius Software Solutions e.U.)과 SHA-256을 검사합니다. 해시는 파일 일치 확인용입니다.\n'+spec['sha256']
            +'\n\n프로그램에 포함된 설치 파일로 설치할까요?')

class DriverCancelled(RuntimeError):
    pass

def verify(path,size=SIZE,sha256=SHA256):
    if path.stat().st_size!=size or hashlib.sha256(path.read_bytes()).hexdigest()!=sha256:
        raise RuntimeError('드라이버 파일 검증 실패 · 설치하지 않았습니다.')

def install(consented=False,cancel=None,progress=None,action='install',component='vigem'):
    if action not in ('install','repair','uninstall','disable_updater','check_update'):raise ValueError('Invalid driver action')
    if component not in ('vigem','hidhide'):raise ValueError('Invalid driver component')
    if action in ('disable_updater','check_update','repair') and component!='hidhide':raise ValueError('Invalid updater component')
    emit=progress or (lambda line:None)
    if consented is not True:raise PermissionError('설치 전 사용자 동의가 필요합니다.')
    if component not in COMPONENTS:raise RuntimeError('드라이버 정보 파일이 없습니다. ZIP 전체를 새 폴더에 압축 해제하세요.')
    if cancel and cancel.is_set():raise DriverCancelled('작업을 취소했습니다.')
    emit('설치 구성요소 확인 중')
    bundle=BUNDLE if component=='vigem' else Path(__file__).resolve().parent/'vendor/hidhide'
    filename=INSTALLER if component=='vigem' else COMPONENTS[component]['filename']
    source=bundle/filename
    helper=bundle/'install-driver.ps1'
    powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    for path in ((source,helper,powershell) if action in ('install','repair') else (helper,powershell)):
        if not path.is_file():raise RuntimeError(f'설치 구성요소가 없습니다: {path.name}. ZIP 전체를 새 폴더에 압축 해제해 주세요.')
    with tempfile.TemporaryDirectory(prefix='DS5Light-driver-') as folder:
        target=Path(folder)/filename
        if action in ('install','repair'):
            shutil.copyfile(source,target)
            if component=='vigem':verify(target)
            else:verify(target,COMPONENTS[component]['size'],COMPONENTS[component]['sha256'])
            emit('설치 파일 SHA256 검증 완료')
        logs=Path(os.environ.get('LOCALAPPDATA',tempfile.gettempdir()))/'DS5Light'/'logs'
        logs.mkdir(parents=True,exist_ok=True)
        log=logs/(component+'-'+action+'-'+uuid.uuid4().hex+'.log')
        emit('상세 로그: '+str(log))
        if cancel and cancel.is_set():raise DriverCancelled('작업을 취소했습니다.')
        emit('Windows 관리자 승인(UAC) 요청 준비 중')
        with subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(helper),'-Installer',str(target),'-Action',action,'-LogPath',str(log)],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW) as process:
            for line in process.stdout:
                line=line.strip()
                if line:
                    translated={'Checking publisher signature...':'게시자 서명 확인 중',
                        'Publisher signature verified.':'게시자 서명 검증 완료',
                        'Waiting for Windows administrator approval (UAC)...':'Windows 관리자 승인(UAC)을 기다리고 있습니다.',
                        'Windows install process started. Waiting for completion...':'Windows 드라이버 설치가 시작되었습니다.',
                        'Windows uninstall process started. Waiting for completion...':'Windows 드라이버 제거가 시작되었습니다.',
                        'Windows install still running; waiting for completion...':'Windows 설치 작업 실행 중 · 완료를 기다리고 있습니다.',
                        'Windows uninstall still running; waiting for completion...':'Windows 제거 작업 실행 중 · 완료를 기다리고 있습니다.',
                        'Windows disable_updater still running; waiting for completion...':'자동 실행 해제 중 · 60초 초과 시 해당 업데이터를 정리하고 결과를 확인합니다.'}
                    emit(translated.get(line,line[:2000]))
            code=process.wait()
        emit(f'Windows 작업 종료 코드: {code}')
        # Vicius --uninstall returns 200 on successful registration removal.
        # The UI must still verify that autostart entries are absent.
        if action=='disable_updater' and code==200:return 0
        if action=='disable_updater' and code==1460:
            emit('자동 실행 해제 작업이 60초 동안 끝나지 않아 해당 업데이터만 종료했습니다. 등록 상태를 다시 확인합니다.')
            from updater_state import verify as verify_registration
            try:emit(verify_registration(False))
            except Exception as exc:raise RuntimeError(f'업데이터 작업 시간 초과 · 자동 실행 OFF 미확인: {exc}. 상세 로그: {log}') from exc
            return 0
        if action=='disable_updater' and code==1461:
            raise RuntimeError(f'업데이터 실행 또는 종료 확인 실패 · 작업 관리자에서 HidHide 업데이터를 확인하세요. 상세 로그: {log}')
        if action=='check_update' and code in (202,203,204,205,209):
            emit({202:'현재 최신 버전입니다.',203:'업데이트 설치 완료 · Windows 재부팅 후 사용하세요.',204:'사용자가 업데이트를 미뤘습니다.',205:'업데이트 확인을 미룬 상태입니다.',209:'사용 중인 프로그램 때문에 업데이트하지 않았습니다.'}[code])
            return code
        if code in (1223,1602):raise DriverCancelled('사용자가 관리자 승인 또는 작업을 취소했습니다.')
        if action=='uninstall' and code==1605:
            emit('제거 대상 버전이 없습니다. 드라이버 연결 상태를 확인합니다.')
            return 0
        if code not in (0,3010):raise RuntimeError(f'드라이버 작업 실패 (코드 {code}). 상세 로그: {log}')
        return code
