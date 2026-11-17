"""Xbox feedback -> Studio USB output; mixing remains in the existing firmware."""
from studio_slots import device_lock
from collections import deque
import threading

def packet(large,small):
    if any(type(n) is not int or not 0<=n<=255 for n in (large,small)):
        raise ValueError('Invalid motor values')
    data=bytearray(48)  # report 0x02 + 47-byte DualSense common payload
    data[0]=2;data[1]=3 if large or small else 0
    data[3]=small;data[4]=large
    # All other Allow flags stay clear: no LED, volume, mic or trigger writes.
    return bytes(data)

class Rumble:
    def __init__(self):
        self.lock=threading.Lock();self.pending=deque();self.enabled=True;self.overflow=False
        self.last=(0,0);self.sent_at=0.;self.wrote=False;self.latest=(0,0);self.closed=False
    def receive(self,large,small):
        # Native callback: bounded memory only, never HID/Tk/audio work.
        with self.lock:
            if self.closed:return
            value=(int(large),int(small));self.latest=value
            if not self.enabled:return
            if self.pending and self.pending[-1]==value:return
            if len(self.pending)>=128:self.overflow=True;self.pending.clear();return
            self.pending.append(value)
    def set_enabled(self,enabled):
        with self.lock:
            if self.enabled!=enabled:
                self.pending.clear()
                if enabled and not self.closed:self.pending.append(self.latest)
            self.enabled=enabled
    def send(self,device,value,now):
        data=packet(*value)
        self.wrote=True  # A short/failed write has an uncertain physical outcome.
        if device.write(data)!=len(data):raise OSError('게임 진동 USB 전송 실패')
        self.last=value;self.sent_at=now
    def pump(self,device,now,paused=False):
        self.set_enabled(not paused)
        with self.lock:
            if self.overflow:raise RuntimeError('게임 진동 큐 초과 · Xbox 모드를 정지합니다.')
            values=[self.pending.popleft() for _ in range(min(32,len(self.pending)))]
        if paused:
            if self.last!=(0,0):self.send(device,(0,0),now)
            return
        for value in values:
            if value!=self.last:self.send(device,value,now)
        # Studio drops stale host rumble after 300ms. Keep a sustained game
        # command alive at 10Hz, only while nonzero; silence has no heartbeat.
        if self.last!=(0,0) and now-self.sent_at>=.1:self.send(device,self.last,now)
    def close(self,device):
        with self.lock:self.closed=True
        self.set_enabled(False)
        if self.wrote:self.send(device,(0,0),0.)

def confirm_studio(device):
    import re
    from studio_slots import StudioClient
    with device_lock():version=StudioClient(device).firmware()
    match=re.fullmatch(r'v?(1)\.(\d+)\.(\d+)',version.strip())
    if not match or int(match[2])<42:
        raise RuntimeError('게임 진동 혼합은 Studio 1.42 이상에서 지원합니다. 펌웨어를 확인하세요.')
    return version
