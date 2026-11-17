"""Explicit-lifetime ViGEm client. Importing this module opens no driver/device."""
import ctypes as c
from pathlib import Path
from cleanup_utils import recover_owners,cleanup_failed_start

SUCCESS = 0x20000000
BUS_NOT_FOUND = 0xE0000001
_LIVE = set()  # Keep callbacks and native owners alive until a successful join.
_PENDING = set()  # Failed teardown owners; recovered before unhiding/restarting.

def pending_cleanup():return bool(_PENDING)

def recover_pending():
    return recover_owners(_PENDING)

class DriverMissing(RuntimeError):
    pass

class Report(c.Structure):
    _fields_ = [('buttons',c.c_uint16),('lt',c.c_uint8),('rt',c.c_uint8),
                ('lx',c.c_int16),('ly',c.c_int16),('rx',c.c_int16),('ry',c.c_int16)]

def library():
    dll=c.CDLL(str(Path(__file__).parent/'vendor/vigem/DS5LightViGEmClient.dll'),use_last_error=True)
    signatures={
        'alloc':([],c.c_void_p),'free':([c.c_void_p],None),
        'connect':([c.c_void_p],c.c_uint32),'disconnect':([c.c_void_p],None),
        'target_x360_alloc':([],c.c_void_p),'target_free':([c.c_void_p],None),
        'target_add':([c.c_void_p,c.c_void_p],c.c_uint32),
        'target_remove':([c.c_void_p,c.c_void_p],c.c_uint32),
        'target_x360_update':([c.c_void_p,c.c_void_p,Report],c.c_uint32),
        'target_x360_register_notification':([c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p],c.c_uint32),
    }
    for name,(args,result) in signatures.items():
        fn=getattr(dll,'vigem_'+name);fn.argtypes=args;fn.restype=result
    dll.ds5light_client_abi.argtypes=[];dll.ds5light_client_abi.restype=c.c_uint32
    if dll.ds5light_client_abi()!=2:raise RuntimeError('전송 오류 처리를 지원하는 최신 Xbox 클라이언트 DLL이 필요합니다.')
    dll.ds5light_x360_stop.argtypes=[c.c_void_p];dll.ds5light_x360_stop.restype=c.c_int
    dll.ds5light_x360_error.argtypes=[c.c_void_p];dll.ds5light_x360_error.restype=c.c_uint32
    return dll

def check(code,operation=None,windows_error=None):
    if code==BUS_NOT_FOUND:raise DriverMissing('ViGEmBus 드라이버가 필요합니다.')
    if code!=SUCCESS:
        detail=f'ViGEm 오류 0x{code:08X}'
        if operation:detail=f'{operation}: {detail}'
        if code==0xE0000017 and windows_error:
            detail+=f' · Windows {windows_error}: {c.FormatError(windows_error).strip()}'
        raise RuntimeError(detail)

def probe():
    """Connect to the bus only; do not create a virtual controller."""
    dll=library();client=dll.vigem_alloc()
    if not client:raise MemoryError('ViGEm allocation failed')
    try:check(dll.vigem_connect(client))
    finally:dll.vigem_disconnect(client);dll.vigem_free(client)

class XboxBackend:
    def __init__(self):
        if pending_cleanup():raise RuntimeError('이전 가상 패드 종료가 남아 있습니다. 보조 도구에서 복구하세요.')
        self.dll=library();self.client=None;self.target=None;self.attached=False;self.callback=None
        try:
            self.client=self.dll.vigem_alloc()
            if not self.client:raise MemoryError('ViGEm allocation failed')
            check(self.dll.vigem_connect(self.client))
            self.target=self.dll.vigem_target_x360_alloc()
            if not self.target:raise MemoryError('Xbox allocation failed')
            code=self.dll.vigem_target_add(self.client,self.target)
            check(code,'가상 Xbox 패드 생성',c.get_last_error());self.attached=True
        except Exception as exc:
            cleanup_failed_start(self,exc);raise
    def update(self,state):
        check(self.dll.vigem_target_x360_update(self.client,self.target,Report(*state)))
    def check_health(self):
        code=self.dll.ds5light_x360_error(self.target)
        if code:raise RuntimeError(f'게임 진동 수신 오류 (Windows 코드 {code})')
    def set_feedback(self,receive):
        if self.callback is not None:raise RuntimeError('Feedback already registered')
        callback_type=c.WINFUNCTYPE(None,c.c_void_p,c.c_void_p,c.c_ubyte,c.c_ubyte,c.c_ubyte,c.c_void_p)
        # The patched native stop joins the thread while ctypes releases the GIL.
        callback=callback_type(lambda client,target,large,small,led,user:receive(large,small))
        self.callback=callback
        _LIVE.add(self)
        check(self.dll.vigem_target_x360_register_notification(self.client,self.target,callback,None))
    def clear_feedback(self):
        if self.callback is not None:
            if not self.dll.ds5light_x360_stop(self.target):
                raise RuntimeError('게임 진동 수신 종료 미확인 · 메모리를 보존했습니다.')
            self.callback=None
    def close(self):
        try:self._close()
        except Exception:
            if self.target or self.client:_PENDING.add(self)
            raise
    def _close(self):
        errors=[]
        self.clear_feedback()
        if self.target:
            if self.attached:
                try:self.update((0,)*7)
                except Exception:pass
                try:check(self.dll.vigem_target_remove(self.client,self.target))
                except Exception as exc:errors.append(str(exc))
            self.dll.vigem_target_free(self.target);self.target=None;self.attached=False
        if self.client:
            self.dll.vigem_disconnect(self.client);self.dll.vigem_free(self.client);self.client=None
        _LIVE.discard(self)
        _PENDING.discard(self)

        if errors:raise RuntimeError("가상 패드 제거 결과 미확인: "+" · ".join(errors))

