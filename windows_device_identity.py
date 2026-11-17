"""Read-only Windows container identity lookup, only on selection/recovery."""
import ctypes as C
from ctypes import wintypes as W
import os,uuid

CONTAINER_FMTID='8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c'
class Key(C.Structure):
    _fields_=[('guid',C.c_ubyte*16),('pid',W.DWORD)]
    def __init__(self,guid,pid):
        super().__init__();C.memmove(C.addressof(self),uuid.UUID(guid).bytes_le,16);self.pid=pid

def hid_instance(path):
    if os.name!='nt' or not path:return None
    try:
        text=path.decode('utf-8') if isinstance(path,bytes) else path
        if not text.startswith('\\\\?\\'):return None
        cm=C.WinDLL('cfgmgr32')
        get_interface=cm.CM_Get_Device_Interface_PropertyW
        get_interface.argtypes=[W.LPCWSTR,C.POINTER(Key),C.POINTER(W.ULONG),C.c_void_p,C.POINTER(W.ULONG),W.ULONG]
        get_interface.restype=W.ULONG
        key=Key('78c34fc8-104a-4aca-9ea4-524d52996e57',256)
        kind=W.ULONG();buf=C.create_unicode_buffer(1024);size=W.ULONG(C.sizeof(buf))
        if get_interface(text,C.byref(key),C.byref(kind),buf,C.byref(size),0)!=0 or kind.value!=18:return None
        return buf.value
    except (OSError,ValueError,UnicodeError,AttributeError):return None


def hid_container(path):
    instance=hid_instance(path)
    if not instance:return None
    try:
        cm=C.WinDLL('cfgmgr32');buf=C.create_unicode_buffer(instance);kind=W.ULONG()
        locate=cm.CM_Locate_DevNodeW;locate.argtypes=[C.POINTER(W.ULONG),W.LPWSTR,W.ULONG];locate.restype=W.ULONG
        node=W.ULONG()
        if locate(C.byref(node),buf,0)!=0:return None
        get_node=cm.CM_Get_DevNode_PropertyW
        get_node.argtypes=[W.ULONG,C.POINTER(Key),C.POINTER(W.ULONG),C.c_void_p,C.POINTER(W.ULONG),W.ULONG];get_node.restype=W.ULONG
        key=Key(CONTAINER_FMTID,2);guid=(C.c_ubyte*16)();size=W.ULONG(16)
        if get_node(node,C.byref(key),C.byref(kind),guid,C.byref(size),0)!=0 or kind.value!=13 or size.value!=16:return None
        value=str(uuid.UUID(bytes_le=bytes(guid)))
        if value=='00000000-0000-0000-0000-000000000000':return None
        return value
    except (OSError,ValueError,UnicodeError,AttributeError):return None
