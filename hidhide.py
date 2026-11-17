"""Scoped HidHide configuration via the official control-device API (UTF-16).
No polling/background helper. Only the selected, confirmed Studio HID is hidden.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import re
import uuid
from driver_state import atomic_json,ps_read
from windows_device_identity import hid_instance

class Missing(RuntimeError):pass

def journal_path():
    return Path(os.environ['LOCALAPPDATA'])/'DS5Light'/'hidhide-session.json'

def own_image():
    api=C.WinDLL('psapi',use_last_error=True)
    fn=api.GetProcessImageFileNameW
    fn.argtypes=[W.HANDLE,W.LPWSTR,W.DWORD];fn.restype=W.DWORD
    buf=C.create_unicode_buffer(32768)
    if not fn(W.HANDLE(-1),buf,len(buf)):raise C.WinError(C.get_last_error())
    return buf.value

class Driver:
    def __enter__(self):
        if os.name!='nt':raise Missing('HidHide는 Windows에서 사용할 수 있습니다.')
        self.api=C.WinDLL('kernel32',use_last_error=True)
        create=self.api.CreateFileW
        create.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];create.restype=W.HANDLE
        self.handle=create(r'\\.\HidHide',0x80000000,7,None,3,0x80,None)
        if self.handle==W.HANDLE(-1).value:
            code=C.get_last_error()
            if code in (2,3):raise Missing('HidHide 드라이버가 없습니다. 설치 직후라면 재부팅하세요.')
            raise RuntimeError('HidHide에 연결할 수 없습니다. 설정 프로그램을 닫고 다시 시도하세요. '+str(C.WinError(code)))
        io=self.api.DeviceIoControl
        io.argtypes=[W.HANDLE,W.DWORD,C.c_void_p,W.DWORD,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p];io.restype=W.BOOL
        self.api.CloseHandle.argtypes=[W.HANDLE];self.api.CloseHandle.restype=W.BOOL
        return self
    def __exit__(self,*args):self.api.CloseHandle(self.handle)
    def io(self,number,data=None,size=0):
        source=C.create_string_buffer(data,len(data)) if data else None
        out=C.create_string_buffer(size) if size else None;used=W.DWORD()
        code=(32769<<16)|(1<<14)|(number<<2)
        if not self.api.DeviceIoControl(self.handle,code,source,len(data) if data else 0,out,size,C.byref(used),None):
            raise C.WinError(C.get_last_error())
        return (out.raw[:used.value] if out else b''),used.value
    def entries(self,number):
        _,needed=self.io(number)
        if needed>1024*1024:raise RuntimeError('HidHide 목록 크기가 비정상입니다.')
        if not needed:return []
        raw,_=self.io(number,size=max(4,needed*2))
        return [s for s in raw.decode('utf-16-le').split('\0') if s]
    def put_entries(self,number,values):
        self.io(number,('\0'.join(values)+'\0\0').encode('utf-16-le'))
    def flag(self,number):
        raw,_=self.io(number,size=1)
        if raw not in (b'\x00',b'\x01'):raise RuntimeError('HidHide 상태 응답이 잘못되었습니다.')
        return raw==b'\x01'
    def active(self,value):self.io(2053,bytes([bool(value)]))

def probe():
    with Driver() as driver:
        return {'active':driver.flag(2052),'inverse':driver.flag(2054)}

def contains(values,value):return value.casefold() in {s.casefold() for s in values}
def without(values,value):return [s for s in values if s.casefold()!=value.casefold()]

def valid_device(value):
    return isinstance(value,str) and bool(re.fullmatch(r'HID\\VID_054C&PID_(?:0CE6|0DF2)[^\\\r\n\x00]*\\[^\\\r\n\x00]+',value,re.I))

class CorruptJournal(RuntimeError):pass

def backup_path(path):return path.with_suffix(path.suffix+'.backup')
def pending(path):return path.exists() or backup_path(path).exists()
def write_journal(path,data):
    atomic_json(path,data)
    atomic_json(backup_path(path),data)

def read_journal(path):
    errors=[]
    for candidate in (path,backup_path(path)):
        if not candidate.exists():continue
        try:
            data=json.loads(candidate.read_text(encoding='utf8'))
            if not isinstance(data,dict):raise ValueError('not an object')
            access=data.get('version')==2 and data.get('device') is None and data.get('added_device') is False and data.get('enabled') is False
            if (data.get('version') not in (1,2,3) or not (access or valid_device(data.get('device'))) or
                not isinstance(data.get('image'),str) or not data['image'].startswith('\\Device\\') or
                any(type(data.get(k)) is not bool for k in ('added_device','added_app','enabled'))):raise ValueError('invalid fields')
            if data['version']==3 and (not isinstance(data.get('saved_devices'),list) or not data['saved_devices'] or any(not isinstance(v,str) or not v or '\0' in v for v in data['saved_devices']) or not data['enabled']):raise ValueError('invalid saved devices')
            if 'untouched' in data and type(data['untouched']) is not bool:raise ValueError('invalid mutation state')
            return data
        except (ValueError,OSError) as exc:errors.append(str(exc))
    raise CorruptJournal('숨김 복구 기록과 사본을 읽을 수 없습니다. 기록 보존 후 HidHide 설정 확인이 필요합니다. '+str(path))

def archive_corrupt():
    archived=[]
    for path in (journal_path(),access_path()):
        if not pending(path):continue
        try:read_journal(path)
        except CorruptJournal:
            for candidate in (path,backup_path(path)):
                if candidate.exists():
                    target=candidate.with_name(candidate.name+'.damaged-'+uuid.uuid4().hex)
                    candidate.rename(target);archived.append(str(target))
    return '손상 기록 보존: '+', '.join(archived)+' · 기존 숨김 목록은 변경하지 않았습니다. HidHide 설정에서 확인하세요.'

def archive_removed():
    """Called only after a consented uninstall succeeds; retain evidence."""
    for path in (journal_path(),access_path()):
        for candidate in (path,backup_path(path)):
            if candidate.exists():candidate.rename(candidate.with_name(candidate.name+'.removed-'+uuid.uuid4().hex))

def access_path():return journal_path().with_name('hidhide-access.json')

def _prepare_access():
    if pending(journal_path()):raise RuntimeError('이전 숨김 기록이 있습니다. 먼저 숨김 복구를 누르세요.')
    path=access_path();image=own_image()
    if pending(path):
        data=read_journal(path)
        if data['image']!=image:recover(path)
    with Driver() as driver:
        if driver.flag(2054):raise RuntimeError('HidHide 반전 모드를 먼저 확인하세요.')
        apps=driver.entries(2048)
        if not pending(path):
            write_journal(path,dict(version=2,device=None,image=image,added_device=False,
                                   added_app=not contains(apps,image),enabled=False))
        if not contains(apps,image):driver.put_entries(2049,apps+[image])
        if not contains(driver.entries(2048),image):raise RuntimeError('DS5Light 접근 허용을 확인하지 못했습니다.')
    return 'DS5Light 원본 입력 접근 준비 완료'

def prepare_access():
    try:return _prepare_access()
    except Exception:
        # Roll back this access preparation only when no device session is pending.
        # Preserve ambiguous/corrupt evidence for the explicit recovery UI.
        if not pending(journal_path()):
            try:recover(access_path())
            except Exception:pass
        raise

def recover(path=None):
    path=path or journal_path()
    if not pending(path):return '복구할 DS5Light 숨김 설정이 없습니다.'
    data=read_journal(path)
    if data.get('untouched',False):
        backup_path(path).unlink(missing_ok=True);path.unlink(missing_ok=True)
        return '장치 설정 변경 전 중단 · 기존 설정 유지'
    with Driver() as driver:
        devices=driver.entries(2050)
        if data['version']==3:
            saved=data['saved_devices']
            same=lambda a,b:{x.casefold() for x in a}=={x.casefold() for x in b}
            active=driver.flag(2052)
            if driver.flag(2054) or not (same(devices,[data['device']]) or same(devices,saved) and not active):
                raise RuntimeError('다른 프로그램이 HidHide 설정을 변경했습니다. 백업을 보존했습니다. 다른 변환 앱 종료 후 숨김 복구를 확인하세요.')
            if active:driver.active(False)
            if not same(devices,saved):driver.put_entries(2051,saved)
            if driver.flag(2052) or not same(driver.entries(2050),saved):raise RuntimeError('기존 숨김 목록 복원 확인 실패')
            apps=driver.entries(2048)
            if data['added_app']:driver.put_entries(2049,without(apps,data['image']))
            if data['added_app'] and contains(driver.entries(2048),data['image']):raise RuntimeError('앱 접근 허용 복구 확인 실패')
            backup_path(path).unlink(missing_ok=True);path.unlink(missing_ok=True)
            return '이전 프로그램의 숨김 목록과 꺼짐 상태를 복원했습니다.'
        if data['added_device']:
            devices=without(devices,data['device']);driver.put_entries(2051,devices)
        if data['enabled'] and not devices:driver.active(False)
        apps=driver.entries(2048)
        if data['added_app']:driver.put_entries(2049,without(apps,data['image']))
        if data['added_device'] and contains(driver.entries(2050),data['device']):raise RuntimeError('숨김 해제 확인 실패')
        if data['added_app'] and contains(driver.entries(2048),data['image']):raise RuntimeError('앱 접근 허용 복구 확인 실패')
        if data['enabled'] and not devices and driver.flag(2052):raise RuntimeError('숨김 상태 복구 확인 실패')
    backup_path(path).unlink(missing_ok=True);path.unlink(missing_ok=True)
    return 'DS5Light가 추가한 숨김 설정 복구 완료 · 필요하면 Pico를 다시 연결하세요.'

def recover_all():
    result=recover()
    other=recover(access_path())
    return result+' / '+other

def diagnostics():
    result={}
    try:
        with Driver() as d:result.update(active=d.flag(2052),inverse=d.flag(2054),hidden_devices=d.entries(2050),allowed_apps=d.entries(2048))
    except Exception as exc:result['driver_error']=str(exc)
    import watchdog_service
    result['watchdog_journal']=watchdog_service.diagnostics()
    result['journals']={}
    for path in (journal_path(),access_path()):
        if pending(path):
            try:result['journals'][path.name]=read_journal(path)
            except Exception as exc:result['journals'][path.name]=str(exc)
    try:
        result['background']=ps_read("Get-CimInstance Win32_Service -Filter \"Name='HidHideWatchdog.exe'\" | Select-Object Name,State,StartMode,PathName | ConvertTo-Json -Compress")
        result['updater_tasks']=ps_read("@(Get-ScheduledTask | Where-Object {$_.TaskName -eq 'nefarius_HidHide_Updater'} | Select-Object TaskName,State) | ConvertTo-Json -Compress")
    except Exception as exc:result['background_error']=str(exc)
    return result

def preflight():
    if pending(journal_path()):raise RuntimeError('이전 숨김 복구 기록이 있습니다. 먼저 숨김 복구를 누르세요.')
    with Driver() as d:
        if d.flag(2054):raise RuntimeError('HidHide 반전 모드에서는 시작할 수 없습니다. 기존 설정을 확인하세요.')
        if d.flag(2052):raise RuntimeError('다른 프로그램의 HidHide 숨김이 켜져 있습니다. 다른 변환 앱에서 숨김을 끄고 종료한 뒤 다시 시도하세요.')
        return d.entries(2050)

class Session:
    def __init__(self,path=None):self.path=path or journal_path();self.owned=False
    def begin(self,device_path,expected=None):
        if pending(self.path):raise RuntimeError('이전 숨김 복구 기록이 있습니다. 먼저 Xbox 창의 숨김 복구를 누르세요.')
        device=hid_instance(device_path)
        if not valid_device(device):raise RuntimeError('Pico 게임패드 HID를 식별하지 못했습니다. 숨기지 않았습니다.')
        image=own_image()
        with Driver() as driver:
            if driver.flag(2054):raise RuntimeError('HidHide의 반전 모드가 켜져 있습니다. 기존 설정을 확인하세요.')
            active=driver.flag(2052);devices=driver.entries(2050);apps=driver.entries(2048)
            if expected is not None and (active or devices!=expected):raise RuntimeError('준비 중 다른 프로그램이 HidHide 설정을 변경했습니다. 다시 확인하세요.')
            data=dict(version=1,device=device,image=image,added_device=not contains(devices,device),
                      added_app=not contains(apps,image),enabled=not active)
            if not active and devices:data.update(version=3,saved_devices=list(devices))
            data['untouched']=True
            self.owned=True
            write_journal(self.path,data)
            if driver.flag(2054) or driver.flag(2052)!=active or driver.entries(2050)!=devices:raise RuntimeError('숨김 변경 직전 외부 설정 변경 감지 · 백업 보존')
            data['untouched']=False;write_journal(self.path,data)
            if data['added_app']:driver.put_entries(2049,apps+[image])
            if data['version']==3:driver.put_entries(2051,[device])
            elif data['added_device']:driver.put_entries(2051,devices+[device])
            if not active:driver.active(True)
            if not driver.flag(2052) or not contains(driver.entries(2050),device) or not contains(driver.entries(2048),image):
                raise RuntimeError('HidHide 설정 확인에 실패했습니다.')
    def close(self):
        if self.owned:return recover(self.path)
