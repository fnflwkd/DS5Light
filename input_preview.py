"""Opt-in USB output preview. Never changes device settings or injects input."""
import threading
import time
from collections import deque
from remapping import BUTTONS
from studio_slots import _DEVICE_LOCK

def button_mask(raw):
    if len(raw)!=64 or raw[0]!=1:raise ValueError('Sony USB 입력 형식이 아닙니다.')
    hat=raw[8]&15
    mask=((raw[8]>>4)<<4)|(raw[9]<<8)|((raw[10]&7)<<16)
    for bit,hats in enumerate(((0,1,7),(3,4,5),(5,6,7),(1,2,3))):
        if hat in hats:mask|=1<<bit
    return mask

class InputPreview:
    def __init__(self):
        self.stop_event=threading.Event();self.thread=None
        self.state=(0,'테스트 꺼짐');self.last_received=None
        self.events=deque(maxlen=128)
    def start(self,path,factory=None):
        self.stop()
        if self.thread and self.thread.is_alive():raise RuntimeError('이전 입력 테스트가 종료 중입니다.')
        self.stop_event=threading.Event();self.state=(0,'입력 대기 중');self.events.clear();self.last_received=None
        self.thread=threading.Thread(target=self.run,args=(path,factory),daemon=True)
        try:self.thread.start()
        except Exception:
            self.thread=None;self.stop_event.set();raise
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=.3)
        self.state=(0,'테스트 꺼짐');self.last_received=None
    def run(self,path,factory):
        device=None
        try:
            if factory is None:
                import hid
                factory=hid.device
            with _DEVICE_LOCK:
                if self.stop_event.is_set():return
                device=factory();device.open_path(path);device.set_nonblocking(1)
            last=time.monotonic();previous=0
            while not self.stop_event.wait(.05):
                # Skip a busy configuration transaction rather than delaying it.
                if not _DEVICE_LOCK.acquire(blocking=False):continue
                try:
                    raw=None
                    for _ in range(256):
                        report=device.read(64)
                        if not report:break
                        mask=button_mask(report)
                        for i,name in enumerate(BUTTONS):
                            if mask&~previous&(1<<i):self.events.append((time.monotonic(),'✕' if name=='×' else name))
                        previous=mask;raw=report
                    else:raise RuntimeError('입력 큐가 밀려 테스트를 중지했습니다.')
                finally:_DEVICE_LOCK.release()
                if raw:
                    mask=button_mask(raw);last=time.monotonic();self.last_received=last
                    self.state=(mask,'PC가 받은 패드 입력')
                elif time.monotonic()-last>1:
                    self.state=(0,'새 입력 없음 · 연결을 확인하세요.');previous=0
        except Exception as exc:self.state=(0,str(exc))
        finally:
            if device:device.close()
            if self.stop_event.is_set():self.state=(0,'테스트 꺼짐');self.last_received=None
