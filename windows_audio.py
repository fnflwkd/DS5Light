"""Read-only Core Audio endpoint/session snapshots. Called only on demand.

Uses IMMDeviceEnumerator, IAudioSessionManager2 and IAudioMeterInformation.
No stream is opened and no system volume or mute setting is changed.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import uuid


class GUID(C.Structure):
    _fields_=[('bytes',C.c_ubyte*16)]
    def __init__(self,value):
        super().__init__(); C.memmove(C.addressof(self),uuid.UUID(value).bytes_le,16)


class PROPERTYKEY(C.Structure):
    _fields_=[('fmtid',GUID),('pid',W.DWORD)]


class VariantData(C.Union):
    _fields_=[('string',C.c_void_p),('raw',C.c_ubyte*16)]


class PROPVARIANT(C.Structure):
    _fields_=[('vt',C.c_ushort),('reserved',C.c_ushort*3),('value',VariantData)]


ENUMERATOR_CLASS=GUID('bcde0395-e52f-467c-8e3d-c4579291692e')
ENUMERATOR_IID=GUID('a95664d2-9614-4f35-a746-de8db63617e6')
MANAGER_IID=GUID('77aa99a0-1bd6-484f-8bc7-2c654c9a9b6f')
SESSION_IID=GUID('bfb7ff88-7239-4fc9-8fa2-07c950be9c6d')
METER_IID=GUID('c02216f6-8c67-4b5b-9d00-d008e73e0064')
CHANNEL_VOLUME_IID=GUID('1c158861-b533-4b30-b1cf-e853e51c59b8')
AUDIO_CLIENT_IID=GUID('1cb9ad4c-dbfa-4c32-b178-c2f568a703b2')
FRIENDLY_NAME=PROPERTYKEY(GUID('a45c254e-df1c-4efd-8020-67d146a850e0'),14)
CONTAINER_ID=PROPERTYKEY(GUID('8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c'),2)


def _call(pointer,index,types,*args):
    table=C.cast(pointer,C.POINTER(C.POINTER(C.c_void_p))).contents
    function=C.WINFUNCTYPE(C.c_long,C.c_void_p,*types)(table[index])
    result=function(pointer,*args)
    if result<0: raise OSError(f'Core Audio 0x{result&0xffffffff:08x}')
    return result


def _release(pointer):
    if pointer and pointer.value:
        _call(pointer,2,())


def _query(pointer,iid):
    result=C.c_void_p()
    _call(pointer,0,(C.POINTER(GUID),C.POINTER(C.c_void_p)),C.byref(iid),C.byref(result))
    return result


def _endpoint_name(endpoint,ole):
    store=C.c_void_p(); value=PROPVARIANT()
    try:
        _call(endpoint,4,(W.DWORD,C.POINTER(C.c_void_p)),0,C.byref(store))
        _call(store,5,(C.POINTER(PROPERTYKEY),C.POINTER(PROPVARIANT)),C.byref(FRIENDLY_NAME),C.byref(value))
        return C.wstring_at(value.value.string) if value.vt==31 and value.value.string else ''
    finally:
        ole.PropVariantClear(C.byref(value)); _release(store)


def _endpoint_container(endpoint,ole):
    store=C.c_void_p();value=PROPVARIANT()
    try:
        _call(endpoint,4,(W.DWORD,C.POINTER(C.c_void_p)),0,C.byref(store))
        _call(store,5,(C.POINTER(PROPERTYKEY),C.POINTER(PROPVARIANT)),C.byref(CONTAINER_ID),C.byref(value))
        if value.vt==72 and value.value.string:
            result=str(uuid.UUID(bytes_le=C.string_at(value.value.string,16)))
            return result if result!='00000000-0000-0000-0000-000000000000' else None
    except OSError:pass
    finally:ole.PropVariantClear(C.byref(value));_release(store)
    return None


def _endpoint_format(endpoint,ole):
    client=C.c_void_p(); fmt=C.c_void_p()
    try:
        _call(endpoint,3,(C.POINTER(GUID),W.DWORD,C.c_void_p,C.POINTER(C.c_void_p)),C.byref(AUDIO_CLIENT_IID),23,None,C.byref(client))
        _call(client,8,(C.POINTER(C.c_void_p),),C.byref(fmt))
        import struct
        tag,channels,rate,_,_,_,extra=struct.unpack('<HHIIHHH',C.string_at(fmt,18))
        mask=struct.unpack('<I',C.string_at(fmt.value+20,4))[0] if tag==65534 and extra>=22 else (3 if channels==2 else None)
        return {'mix_channels':channels,'channel_mask':mask,'mix_rate':rate}
    except OSError:return {}
    finally:
        if fmt.value:ole.CoTaskMemFree(fmt)
        _release(client)


def _merge_session(result,pid,peak,channels):
    """Keep known zero and maximum channel evidence across all sessions."""
    previous=result.get(pid,{})
    peaks=[v for v in (previous.get('peak'),peak) if v is not None]
    result[pid]={'active':True,'peak':max(peaks) if peaks else None,
                 'channels':max(previous.get('channels') or 0,channels or 0) or None}


def _read_sessions(endpoint,channel_pid=None):
    manager=C.c_void_p(); enumerator=C.c_void_p(); result={}
    complete=True
    try:
        _call(endpoint,3,(C.POINTER(GUID),W.DWORD,C.c_void_p,C.POINTER(C.c_void_p)),
              C.byref(MANAGER_IID),23,None,C.byref(manager))
        _call(manager,5,(C.POINTER(C.c_void_p),),C.byref(enumerator))
        count=C.c_int(); _call(enumerator,3,(C.POINTER(C.c_int),),C.byref(count))
        for index in range(count.value):
            control=C.c_void_p(); control2=C.c_void_p(); meter=C.c_void_p(); volume=C.c_void_p()
            try:
                _call(enumerator,4,(C.c_int,C.POINTER(C.c_void_p)),index,C.byref(control))
                state=C.c_int(); _call(control,3,(C.POINTER(C.c_int),),C.byref(state))
                if state.value!=1: continue
                control2=_query(control,SESSION_IID)
                pid=W.DWORD(); _call(control2,14,(C.POINTER(W.DWORD),),C.byref(pid))
                if not pid.value: continue
                peak=None
                try:
                    meter=_query(control,METER_IID)
                    value=C.c_float(); _call(meter,3,(C.POINTER(C.c_float),),C.byref(value))
                    peak=max(0.,min(1.,value.value))
                except OSError: pass
                channels=None
                if channel_pid==pid.value:
                    try:
                        volume=_query(control,CHANNEL_VOLUME_IID)
                        count=W.UINT();_call(volume,3,(C.POINTER(W.UINT),),C.byref(count))
                        if count.value in (1,2,6,8):channels=count.value
                    except OSError:pass
                _merge_session(result,pid.value,peak,channels)
            except OSError:
                # A session can disappear while being enumerated.
                complete=False
                continue
            finally:
                _release(volume); _release(meter); _release(control2); _release(control)
        return result,complete
    finally:
        _release(enumerator); _release(manager)


def snapshot(include_sessions=True,channel_pid=None):
    result={'endpoints':[],'sessions':{},'complete':False}
    if os.name!='nt': return result
    ole=C.WinDLL('ole32')
    ole.CoInitializeEx.argtypes=[C.c_void_p,W.DWORD]; ole.CoInitializeEx.restype=C.c_long
    ole.CoCreateInstance.argtypes=[C.POINTER(GUID),C.c_void_p,W.DWORD,C.POINTER(GUID),C.POINTER(C.c_void_p)]
    ole.CoCreateInstance.restype=C.c_long
    ole.CoTaskMemFree.argtypes=[C.c_void_p]
    ole.PropVariantClear.argtypes=[C.POINTER(PROPVARIANT)]
    initialized=ole.CoInitializeEx(None,0)
    if initialized<0 and initialized&0xffffffff!=0x80010106: return result
    enumerator=C.c_void_p(); collection=C.c_void_p()
    try:
        hr=ole.CoCreateInstance(C.byref(ENUMERATOR_CLASS),None,1,C.byref(ENUMERATOR_IID),C.byref(enumerator))
        if hr<0: return result
        _call(enumerator,3,(C.c_int,W.DWORD,C.POINTER(C.c_void_p)),0,1,C.byref(collection))
        count=W.UINT(); _call(collection,3,(C.POINTER(W.UINT),),C.byref(count))
        complete=True
        for index in range(count.value):
            endpoint=C.c_void_p(); identifier=C.c_void_p()
            try:
                _call(collection,4,(W.UINT,C.POINTER(C.c_void_p)),index,C.byref(endpoint))
                _call(endpoint,5,(C.POINTER(C.c_void_p),),C.byref(identifier))
                name=_endpoint_name(endpoint,ole)
                entry={'id':C.wstring_at(identifier),'name':name,'container_id':_endpoint_container(endpoint,ole)}
                if not include_sessions:entry.update(_endpoint_format(endpoint,ole))
                result['endpoints'].append(entry)
                if include_sessions:
                    sessions,sessions_complete=_read_sessions(endpoint,channel_pid)
                    complete=complete and sessions_complete
                    for pid,session in sessions.items():
                        _merge_session(result['sessions'],pid,session.get('peak'),session.get('channels'))
            except OSError: complete=False
            finally:
                if identifier.value: ole.CoTaskMemFree(identifier)
                _release(endpoint)
        result['complete']=complete
    except OSError: pass
    finally:
        _release(collection); _release(enumerator)
        if initialized>=0: ole.CoUninitialize()
    return result


def attach_endpoint_ids(devices,endpoints=None):
    endpoints=snapshot(False)['endpoints'] if endpoints is None else endpoints
    for device in devices:
        name=device['name'].removesuffix(' [Loopback]') if device.get('isLoopbackDevice') else device['name']
        matches=[entry for entry in endpoints if entry['name']==name]
        peers=[d for d in devices if d['name']==device['name'] and bool(d.get('isLoopbackDevice'))==bool(device.get('isLoopbackDevice'))]
        if len(matches)==1 and len(peers)==1:
            device.update({k:v for k,v in matches[0].items() if k not in ('name','id')})
            device['endpoint_id']=matches[0]['id']
    return devices
