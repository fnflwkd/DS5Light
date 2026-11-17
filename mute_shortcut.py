"""Opt-in Sony USB mute edge input. No BT decoder or broad support claims."""
import ctypes as C
from ctypes import wintypes as W
import threading, time
from studio_slots import devices, _DEVICE_LOCK
from device_binding import resolve_hid

KEYS={**{f'F{i}':0x6f+i for i in range(1,25)},**{chr(i):i for i in range(65,91)},
      **{str(i):0x30+i for i in range(10)},'CTRL':0x11,'SHIFT':0x10,'ALT':0x12,'SPACE':0x20}
def parse_keys(text):
    parts=[p.strip().upper() for p in text.split('+')]
    if not 1<=len(parts)<=4 or len(set(parts))!=len(parts) or any(p not in KEYS for p in parts):raise ValueError('Use one key or CTRL/SHIFT/ALT + key (A–Z, 0–9, F1–F24, SPACE)')
    if any(p not in ('CTRL','SHIFT','ALT') for p in parts[:-1]):raise ValueError('Modifiers must come first')
    if parts[-1] in ('CTRL','SHIFT','ALT'):raise ValueError('Select a final key')
    return [KEYS[p] for p in parts]

class KeyInput(C.Structure):
    _fields_=[('vk',W.WORD),('scan',W.WORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
class InputUnion(C.Union):
    _fields_=[('ki',KeyInput),('padding',C.c_byte*32)]
class Input(C.Structure):
    _fields_=[('type',W.DWORD),('u',InputUnion)]

class WindowsKeys:
    def __init__(self):
        self.api=C.WinDLL('user32',use_last_error=True)
        self.api.SendInput.argtypes=[W.UINT,C.POINTER(Input),C.c_int];self.api.SendInput.restype=W.UINT
        self.api.GetForegroundWindow.restype=W.HWND
        self.api.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    def down(self,key):return bool(self.api.GetAsyncKeyState(key)&0x8000)
    def own_window(self):
        import os
        pid=W.DWORD();self.api.GetWindowThreadProcessId(self.api.GetForegroundWindow(),C.byref(pid));return pid.value==os.getpid()
    def send(self,key,up=False):
        item=Input(1,InputUnion(ki=KeyInput(key,0,2 if up else 0,0,0)))
        return self.api.SendInput(1,C.byref(item),C.sizeof(Input))==1

class KeyInjector:
    def __init__(self,api):self.api=api;self.held=[]
    def cleanup(self):
        for key in list(reversed(self.held)):
            if self.api.send(key,True):self.held.remove(key)
        return not self.held
    def fire(self,keys):
        if self.held or self.api.own_window() or any(self.api.down(k) for k in keys):return False
        ok=True
        try:
            for key in keys:
                if not self.api.send(key):ok=False;break
                self.held.append(key)
        finally:ok=self.cleanup() and ok
        return ok

class MuteEdge:
    def __init__(self):self.previous=None
    def read(self,raw):
        if len(raw)!=64 or raw[0]!=1:raise ValueError('Unsupported input report; only Sony USB 0x01/64 bytes')
        pressed=bool(raw[10]&4);fire=self.previous is False and pressed;self.previous=pressed;return fire

def read_latest(device):
    """Drain a bounded batch; ordinary USB report batching is not stale input."""
    raw=device.read(64)
    if raw:
        for _ in range(256):
            newer=device.read(64)
            if not newer:break
            raw=newer
        else:raise RuntimeError('Input backlog; refresh')
    return raw

class ShortcutMonitor:
    def __init__(self):self.stop_event=threading.Event();self.thread=None;self.status='OFF';self.selection=None;self.injector=None
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=1)
        if self.injector and self.injector.held:self.status='Key release failed; check keyboard state'
        else:self.status='OFF' if not self.thread or not self.thread.is_alive() else 'Stopping'
    def start(self,path,keys):
        parsed=parse_keys(keys)
        if self.selection==(path,tuple(parsed)) and self.thread and self.thread.is_alive() and not self.stop_event.is_set():return
        self.stop()
        if self.thread and self.thread.is_alive():return
        if self.injector and self.injector.held:return
        self.selection=(path,tuple(parsed))
        self.stop_event=threading.Event();self.status='Input support unconfirmed'
        self.thread=threading.Thread(target=self.run,args=(path,parsed),daemon=True)
        try:self.thread.start()
        except Exception:
            self.thread=None;self.stop_event.set();raise
    def run(self,path,keys):
        import hid
        d=None;injector=None;edge=MuteEdge()
        try:
            if self.stop_event.is_set():return
            injector=KeyInjector(WindowsKeys());self.injector=injector
            rows=devices();row=resolve_hid(rows,{'path':path})
            if row is None:raise RuntimeError('Selected input absent/ambiguous')
            with _DEVICE_LOCK:
                if self.stop_event.is_set():return
                d=hid.device();d.open_path(row['path']);d.set_nonblocking(1)
                read_latest(d)  # Discard initial queued/held input.
            last=time.monotonic();next_identity=last+2
            while not self.stop_event.wait(.01):
                now=time.monotonic()
                if now>=next_identity:
                    current=resolve_hid(devices(),row)
                    if current is None or current['path']!=row['path']:raise RuntimeError('Input disconnected; refresh')
                    next_identity=now+2
                with _DEVICE_LOCK:
                    if self.stop_event.is_set():break
                    raw=read_latest(d)
                now=time.monotonic()  # Include time spent waiting for feature I/O.
                if not raw:
                    if now-last>2:edge.previous=None;self.status='Input unconfirmed / no fresh reports'
                    continue
                if now-last>.2:edge.previous=None
                last=now;fire=edge.read(raw);self.status='USB input observed · active window'
                if fire and not self.stop_event.is_set():
                    self.status='Key accepted by Windows' if injector.fire(keys) else 'Key skipped/partial failure'
                    if injector.held:raise RuntimeError('Key release failed')
        except Exception as exc:self.status=str(exc)
        finally:
            if injector:
                for _ in range(2):
                    if injector.cleanup():break
                if injector.held:self.status='Key release failed; check keyboard state'
            if d:d.close()
