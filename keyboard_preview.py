"""Temporary Raw Input observer, restricted to the selected Pico container."""
import ctypes as C
from ctypes import wintypes as W
from key_capture import VK
from windows_device_identity import hid_container

class Device(C.Structure):
    _fields_=[('handle',W.HANDLE),('kind',W.DWORD)]
class Registration(C.Structure):
    _fields_=[('page',W.USHORT),('usage',W.USHORT),('flags',W.DWORD),('window',W.HWND)]
class Header(C.Structure):
    _fields_=[('kind',W.DWORD),('size',W.DWORD),('device',W.HANDLE),('param',W.WPARAM)]
class Key(C.Structure):
    _fields_=[('scan',W.USHORT),('flags',W.USHORT),('reserved',W.USHORT),('vk',W.USHORT),('message',W.UINT),('extra',W.ULONG)]

def key_name(vk,scan,flags):
    if vk==16:return 'RSHIFT' if scan==54 else 'SHIFT'
    if vk in (17,18):return ('R' if flags&2 else '')+('CTRL' if vk==17 else 'ALT')
    if vk==13 and flags&2:return 'NUMENTER'
    if not flags&2 and vk in (12,33,34,35,36,37,38,39,40,45,46):
        return {82:'NUM0',79:'NUM1',80:'NUM2',81:'NUM3',75:'NUM4',76:'NUM5',77:'NUM6',71:'NUM7',72:'NUM8',73:'NUM9',83:'NUMDECIMAL'}.get(scan,VK.get(vk))
    return {20:'CAPSLOCK',44:'PRINTSCREEN',144:'NUMLOCK',145:'SCROLLLOCK',19:'PAUSE',91:'WIN',92:'RWIN',160:'SHIFT',161:'RSHIFT',162:'CTRL',163:'RCTRL',164:'ALT',165:'RALT'}.get(vk,VK.get(vk))

class KeyboardPreview:
    def __init__(self):self.old=None;self.callback=None;self.held=set();self.error='';self.allowed=set();self.registered=False
    def start(self,hwnd,path,emit):
        if self.stop() is False:raise RuntimeError(self.error)
        container=hid_container(path)
        if not container:raise RuntimeError('키보드 입력의 Pico 식별 정보를 확인하지 못했습니다.')
        self.user=C.WinDLL('user32',use_last_error=True);u=self.user
        u.GetRawInputDeviceList.argtypes=[C.POINTER(Device),C.POINTER(W.UINT),W.UINT];u.GetRawInputDeviceList.restype=W.UINT
        u.GetRawInputDeviceInfoW.argtypes=[W.HANDLE,W.UINT,C.c_void_p,C.POINTER(W.UINT)];u.GetRawInputDeviceInfoW.restype=W.UINT
        u.GetRawInputData.argtypes=[W.HANDLE,W.UINT,C.c_void_p,C.POINTER(W.UINT),W.UINT];u.GetRawInputData.restype=W.UINT
        u.RegisterRawInputDevices.argtypes=[C.POINTER(Registration),W.UINT,W.UINT];u.RegisterRawInputDevices.restype=W.BOOL
        u.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_void_p];u.SetWindowLongPtrW.restype=C.c_void_p
        u.CallWindowProcW.argtypes=[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.CallWindowProcW.restype=C.c_ssize_t
        count=W.UINT()
        if u.GetRawInputDeviceList(None,C.byref(count),C.sizeof(Device))==0xffffffff:raise OSError('키보드 목록 조회 실패')
        devices=(Device*count.value)();n=u.GetRawInputDeviceList(devices,C.byref(count),C.sizeof(Device))
        if n==0xffffffff:raise OSError('키보드 목록 변경 · 다시 시작하세요.')
        self.allowed=set()
        for d in devices[:n]:
            if d.kind!=1:continue
            size=W.UINT()
            if u.GetRawInputDeviceInfoW(d.handle,0x20000007,None,C.byref(size))==0xffffffff:continue
            buf=C.create_unicode_buffer(size.value+1);size.value+=1
            if u.GetRawInputDeviceInfoW(d.handle,0x20000007,buf,C.byref(size))!=0xffffffff and hid_container(buf.value)==container:self.allowed.add(d.handle)
        if not self.allowed:raise RuntimeError('Pico 키보드 연결 없음 · 키보드 매핑 적용 후 테스트하세요.')
        self.hwnd=hwnd;self.emit=emit;self.error='';self.held.clear()
        prototype=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
        self.callback=prototype(self.proc)
        self.old=u.SetWindowLongPtrW(hwnd,-4,C.cast(self.callback,C.c_void_p))
        if not self.old:raise C.WinError(C.get_last_error())
        r=Registration(1,6,0x100,hwnd)
        if not u.RegisterRawInputDevices(C.byref(r),1,C.sizeof(r)):
            error=C.WinError(C.get_last_error());self.stop();raise error
        self.registered=True
    def proc(self,hwnd,message,wparam,lparam):
        if message==0xff:
            try:
                size=W.UINT();u=self.user
                if u.GetRawInputData(lparam,0x10000003,None,C.byref(size),C.sizeof(Header))!=0xffffffff and C.sizeof(Header)+C.sizeof(Key)<=size.value<=4096:
                    buf=C.create_string_buffer(size.value)
                    if u.GetRawInputData(lparam,0x10000003,buf,C.byref(size),C.sizeof(Header))==size.value:
                        header=Header.from_buffer(buf)
                        if header.kind==1 and header.device in self.allowed:
                            key=Key.from_buffer(buf,C.sizeof(Header));name=key_name(key.vk,key.scan,key.flags)
                            token=(header.device,key.scan,key.flags&6)
                            if key.flags&1:self.held.discard(token)
                            elif token not in self.held:
                                self.held.add(token)
                                if name:self.emit(name)
            except Exception as exc:self.error=str(exc)
        return self.user.CallWindowProcW(self.old,hwnd,message,wparam,lparam)
    def stop(self):
        errors=[]
        if self.registered or self.old:
            r=Registration(1,6,1,None)
            try:
                if not self.user.RegisterRawInputDevices(C.byref(r),1,C.sizeof(r)):raise OSError('키보드 관측 해제 실패')
                self.registered=False
            except Exception as exc:self.registered=True;errors.append(str(exc))
        if self.old:
            try:
                if not self.user.SetWindowLongPtrW(self.hwnd,-4,self.old):raise OSError('키보드 관측 창 복원 실패')
                self.old=None;self.callback=None
            except Exception as exc:errors.append(str(exc))
        # Keep the callback alive if Windows still owns its function pointer.
        self.held.clear();self.allowed.clear();self.error=' · '.join(errors)
        return not errors
