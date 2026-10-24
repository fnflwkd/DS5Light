"""On-demand CPU sorting. No background sampler or additional package dependency."""
import os,time,ctypes
from ctypes import wintypes

EXCLUDED={'system','system idle process','registry','svchost.exe','conhost.exe','csrss.exe','smss.exe','wininit.exe','services.exe','lsass.exe','fontdrvhost.exe','dwm.exe','tasklist.exe','processcapture.exe'}

def processes():
    # Direct Unicode process enumeration: no tasklist subprocess or console encoding.
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('pid',wintypes.DWORD),
                  ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                  ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),('name',wintypes.WCHAR*260)]
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD];k.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    k.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];k.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    h=k.CreateToolhelp32Snapshot(2,0)
    if h==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry=Entry();entry.dwSize=ctypes.sizeof(entry);rows=[]
        ok=k.Process32FirstW(h,ctypes.byref(entry))
        if not ok:raise ctypes.WinError(ctypes.get_last_error())
        while ok:
            if entry.pid and entry.name.casefold() not in EXCLUDED:rows.append((entry.name,entry.pid))
            ok=k.Process32NextW(h,ctypes.byref(entry))
        if ctypes.get_last_error()!=18:raise ctypes.WinError(ctypes.get_last_error())
        return sorted(rows,key=lambda r:(r[0].casefold(),r[1]))
    finally:k.CloseHandle(h)


def cpu_times(rows):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    result={}
    def number(ft):return (ft.dwHighDateTime<<32)|ft.dwLowDateTime
    for name,pid in rows:
        h=kernel.OpenProcess(0x1000,False,pid)
        if not h:continue
        try:
            created,exited,k,u=(wintypes.FILETIME() for _ in range(4))
            if kernel.GetProcessTimes(h,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(k),ctypes.byref(u)):
                result[pid]=(number(created),(number(k)+number(u))/1e7)
        finally:kernel.CloseHandle(h)
    return result

def rank(rows,before,after,seconds,cores):
    result=[]
    for name,pid in rows:
        a=before.get(pid);b=after.get(pid);value=None
        if a and b and a[0]==b[0] and seconds>0:
            value=min(100.,max(0.,(b[1]-a[1])/seconds/max(1,cores)*100))
        result.append((name,pid,value))
    return sorted(result,key=lambda x:(x[2] is None,-(x[2] or 0),x[0].casefold(),x[1]))

def process_list(order='name'):
    rows=[r for r in processes() if r[1]!=os.getpid()]
    if order=='name':return [(name,pid,None) for name,pid in rows]
    if order!='cpu':raise ValueError('Unknown process sort order')
    start=time.perf_counter();before=cpu_times(rows);time.sleep(.5)
    after=cpu_times(rows);elapsed=time.perf_counter()-start
    return rank(rows,before,after,elapsed,os.cpu_count() or 1)
