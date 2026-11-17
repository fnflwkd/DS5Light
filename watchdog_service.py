"""On-demand troubleshooting only; no Xbox lifecycle service ownership."""
import base64
import json
import os
import subprocess
import uuid
from pathlib import Path
from driver_state import atomic_json, powershell, ps_read
from safe_notify import notify

SERVICE = 'HidHideWatchdog.exe'

class Missing(RuntimeError):pass
class CorruptJournal(RuntimeError):pass
class Cancelled(RuntimeError):pass

def journal_path():return Path(os.environ['LOCALAPPDATA'])/'DS5Light'/'watchdog-session.json'
def backup_path(path):return path.with_suffix(path.suffix+'.backup')
def pending(path):return path.exists() or backup_path(path).exists()
def clear(path):
    backup_path(path).unlink(missing_ok=True);path.unlink(missing_ok=True)
def write(path,data):
    atomic_json(path,data);atomic_json(backup_path(path),data)
def read(path):
    for candidate in (path,backup_path(path)):
        if not candidate.exists():continue
        try:
            data=json.loads(candidate.read_text(encoding='utf8'))
            if (isinstance(data,dict) and type(data.get('version')) is int and data['version']==1
                    and data.get('pending') is True and type(data.get('cancelled',False)) is bool):
                return data
        except (ValueError,OSError):pass
    raise CorruptJournal('Watchdog 복구 기록과 사본을 읽을 수 없습니다. 기록 보존 후 서비스 확인이 필요합니다.')
def archive(path=None):
    path=path or journal_path();saved=[]
    for candidate in (path,backup_path(path)):
        if candidate.exists():
            target=candidate.with_name(candidate.name+'.archived-'+uuid.uuid4().hex)
            candidate.rename(target);saved.append(str(target))
    return 'Watchdog 기록 보존: '+', '.join(saved)
def diagnostics():
    path=journal_path()
    if not pending(path):return {'pending':False}
    try:return {'pending':True,'record':read(path)}
    except Exception as exc:return {'pending':True,'error':str(exc)}

def state():
    raw = ps_read(f"Get-CimInstance Win32_Service -Filter \"Name='{SERVICE}'\" | Select-Object State,ProcessId,StartMode | ConvertTo-Json -Compress")
    if not raw:raise Missing('HidHide Watchdog 서비스가 없습니다. 드라이버 확인·설치에서 복구 설치하세요.')
    return json.loads(raw)

def control(action):
    # Only fixed service commands are elevated; no caller-supplied script or path.
    if action not in ('start','stop','manual'):raise ValueError('지원하지 않는 Watchdog 명령')
    script = "$ErrorActionPreference='Stop'; try { $s=Get-Service -Name '" + SERVICE + "'; "
    if action=='manual':
        script += "Set-Service -InputObject $s -StartupType Manual; "
    else:
        target,source,command={'start':('Running','Stopped','Start-Service'),'stop':('Stopped','Running','Stop-Service')}[action]
        script += f"if ($s.Status -eq '{target}') {{ exit 10 }}; if ($s.Status -ne '{source}') {{ throw 'Service is transitioning' }}; {command} -InputObject $s; $s.WaitForStatus('{target}',[TimeSpan]::FromSeconds(15)); "
    script += "exit 0 } catch { exit 1 }"
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    outer = "$ErrorActionPreference='Stop'; try { $p=Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList '-NoProfile','-NonInteractive','-EncodedCommand','" + encoded + "' -Verb RunAs -WindowStyle Hidden -PassThru; $null=$p.Handle; $p.WaitForExit(); exit $p.ExitCode } catch { if ($_.Exception.NativeErrorCode -eq 1223) { exit 1223 }; exit 1 }"
    # Wait for UAC instead of killing an already-elevated operation on timeout.
    r = subprocess.run([powershell(),'-NoProfile','-NonInteractive','-Command',outer],
                       capture_output=True,creationflags=0x08000000)
    if r.returncode==1223:raise Cancelled('Watchdog 관리자 승인을 취소했습니다.')
    if r.returncode not in (0,10):
        raise RuntimeError(f'Watchdog 서비스 {action} 실패 (코드 {r.returncode})')
    return r.returncode

def ensure_running(report=lambda text:None):
    """Start a stopped service once; never own it or schedule a later stop."""
    current=state()['State']
    if current=='Running':return
    if current!='Stopped':raise RuntimeError('Watchdog 상태가 전환 중입니다. 잠시 후 다시 켜 주세요.')
    notify(report,'Watchdog 시작 · 관리자 승인을 기다립니다. Xbox 종료 후에도 유지합니다.')
    control('start')
    if state()['State']!='Running':raise RuntimeError('Watchdog 시작을 확인하지 못했습니다. 다시 켜 주세요.')
    notify(report,'Watchdog 실행 확인 · 종료 시 중지하지 않습니다.')


def ensure_stopped(report=lambda text:None):
    """Explicit user action only; never called by Xbox lifecycle."""
    current=state()['State']
    if current=='Stopped':return
    if current!='Running':raise RuntimeError('Watchdog 상태가 전환 중입니다. 잠시 후 다시 확인하세요.')
    notify(report,'Watchdog 끄기 · 관리자 승인을 기다립니다.')
    control('stop')
    if state()['State']!='Stopped':raise RuntimeError('Watchdog 중지를 확인하지 못했습니다. 상태를 다시 확인하세요.')
    notify(report,'Watchdog OFF 확인 · 서비스 시작 유형은 변경하지 않았습니다.')


def ensure_manual(report=lambda text:None):
    """Explicit start-type change; never starts or stops the service."""
    current=state().get('StartMode')
    if current=='Manual':return
    if current!='Auto':raise RuntimeError('자동 시작 상태에서만 수동으로 바꿀 수 있습니다. 상태를 다시 확인하세요.')
    notify(report,'Watchdog 시작 유형을 수동으로 변경 · 관리자 승인을 기다립니다.')
    control('manual')
    if state().get('StartMode')!='Manual':raise RuntimeError('수동 시작 설정을 확인하지 못했습니다. 상태를 다시 확인하세요.')
    notify(report,'Watchdog 시작 유형: 수동 확인 · 실행 상태는 변경하지 않았습니다.')
