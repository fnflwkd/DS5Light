"""On-demand Windows keyboard/mouse enumeration, never a polling service."""
import ctypes as C
from ctypes import wintypes as W
import time
from dataclasses import dataclass,replace
from windows_device_identity import hid_container
from remapping import device_operation

def raw_input_paths():
    class Device(C.Structure):
        _fields_=[('handle',W.HANDLE),('kind',W.DWORD)]
    user=C.WinDLL('user32',use_last_error=True)
    listing=user.GetRawInputDeviceList
    listing.argtypes=[C.POINTER(Device),C.POINTER(W.UINT),W.UINT];listing.restype=W.UINT
    info=user.GetRawInputDeviceInfoW
    info.argtypes=[W.HANDLE,W.UINT,C.c_void_p,C.POINTER(W.UINT)];info.restype=W.UINT
    for _ in range(3):
        count=W.UINT()
        if listing(None,C.byref(count),C.sizeof(Device))==0xffffffff:raise OSError('Windows input list unavailable')
        devices=(Device*count.value)()
        n=listing(devices,C.byref(count),C.sizeof(Device))
        if n==0xffffffff:continue
        result=[]
        for item in devices[:n]:
            if item.kind not in (0,1):continue
            size=W.UINT()
            if info(item.handle,0x20000007,None,C.byref(size))==0xffffffff:continue
            buf=C.create_unicode_buffer(size.value+1);size.value+=1
            if info(item.handle,0x20000007,buf,C.byref(size))!=0xffffffff:
                result.append(('keyboard' if item.kind==1 else 'mouse',buf.value))
        return result
    raise OSError('Windows input list changed repeatedly')

def interfaces(container):
    if not container:raise RuntimeError('Pico 2 W 식별 정보를 확인할 수 없습니다. 다시 읽어 주세요.')
    return {kind for kind,path in raw_input_paths() if hid_container(path)==container}

def needed_interfaces(snapshot):
    needed=set()
    for i,row in enumerate(snapshot.rows):
        if snapshot.disabled&(1<<i):continue
        if row[17]==0 and any(row[7:11]):needed.add('keyboard')
        if 11<=row[17]<=15:needed.add('mouse')
    return needed

@dataclass(frozen=True)
class Applied:
    snapshot: object
    message: str

def live_baseline(client,original):
    # Restoring the temporary Xbox mask can set the firmware edited indicator.
    # Accept only that metadata change; every identity, definition and flag must match.
    current=client.read()
    profile=dict(original.profile)
    if 'edited' in current.profile:profile['edited']=current.profile['edited']
    if replace(original,profile=profile)!=current:raise RuntimeError('장치 리맵이 변경되었습니다. 다시 읽은 뒤 편집하세요.')
    return current

def apply_connected(path,original,rows,mask,disable_ps,backup,valid=lambda:True,*,ps_enabled=None,live=False,temporary=False):
    def apply(c):
        from temporary_remap import temporary as apply_temporary,saved
        # The edited indicator is metadata in native mode too. All actual remap
        # values and profile identity are still checked by the fresh pre-write read.
        if temporary:return apply_temporary(c,path,original,rows,mask,backup,ps_enabled,allow_edited=True)
        return saved(c,path,original,rows,mask,disable_ps,backup,ps_enabled,allow_edited=True)
    result=device_operation(path,apply,valid)
    connected=ensure_connected(path,result,valid)
    return Applied(result,'임시 적용 완료 · 프로그램 종료 시 원래 리맵으로 복원합니다. '+connected.message) if temporary else connected

def ensure_connected(path,result,valid=lambda:True):
    needed=needed_interfaces(result)
    if not needed:return Applied(result,'Pico 2 W에 버튼 설정을 적용했습니다.')
    try:
        container=hid_container(path)
        if needed<=interfaces(container):return Applied(result,'설정 적용 완료 · Windows 키보드/마우스 연결 확인됨')
        # Re-read the exact snapshot before the one deliberate USB reconnect.
        # Do not flash-save general settings or restart/reflash the Pico.
        try:device_operation(path,lambda c:c.reconnect_usb(result),valid)
        except OSError:pass  # Disconnect can terminate the write after delivery; never resend.
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if not valid():raise RuntimeError('연결 확인이 취소되었습니다.')
            if needed<=interfaces(container):
                return Applied(result,'설정 적용 완료 · Pico 2 W 키보드/마우스 연결을 복구했습니다.')
            time.sleep(.25)
        return Applied(result,'설정은 저장했지만 Windows 키보드/마우스 연결을 확인하지 못했습니다. 다시 읽고 적용해 주세요.')
    except Exception as e:
        return Applied(result,'설정은 저장했지만 키보드/마우스 연결 확인 실패: '+str(e))


def apply_common_connected(path,original,rows,mask,disable_ps,backup,valid=lambda:True,progress=lambda text:None,*,ps_enabled=None):
    from temporary_remap import pending
    if pending(path):raise RuntimeError('임시 리맵을 먼저 복원한 뒤 공통 저장하세요.')
    from common_remap import CommonRemap
    result,count=device_operation(path,lambda c:CommonRemap(c,progress).apply(original,rows,mask,disable_ps,backup,ps_enabled=ps_enabled),valid)
    connection=ensure_connected(path,result,valid)
    return Applied(result,f'저장된 Studio 프로필 {count}개 공통 적용 완료 · '+connection.message)
