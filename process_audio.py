"""Windows per-process loopback helper transport. Fail closed, never full-system fallback."""
import csv
import io
import struct
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

HELPER=Path(__file__).with_name('ProcessCapture.exe')

def processes():
    result=subprocess.run(['tasklist.exe','/FO','CSV','/NH'],capture_output=True,timeout=8,creationflags=0x08000000)
    if result.returncode: raise RuntimeError('프로그램 목록 조회 실패')
    import locale
    rows=csv.reader(io.StringIO(result.stdout.decode(locale.getpreferredencoding(False),errors='replace')))
    excluded={'system','system idle process','registry','svchost.exe','conhost.exe','csrss.exe','smss.exe','wininit.exe','services.exe','lsass.exe','fontdrvhost.exe','dwm.exe','tasklist.exe','processcapture.exe'}
    out=[]
    for row in rows:
        if len(row)>1 and row[1].isdigit() and row[0].lower() not in excluded:
            out.append((row[0],int(row[1])))
    return sorted(out,key=lambda x:(x[0].lower(),x[1]))

class ProcessCaptureStream:
    def __init__(self,pid,channels=6):
        if channels not in (2,6): raise ValueError('게임 캡처 채널은 2 또는 6')
        self.pid,self.channels=pid,channels
        self.closed=False; self.error=None; self.ready=threading.Event()
        self.lock=threading.Lock(); self.queue=deque(maxlen=8); self.pending=bytearray()
        self.pending_time=0.0
        self.drops=0; self.stale=0; self.messages=deque(maxlen=12)
        self.child=subprocess.Popen([str(HELPER),str(pid),str(channels)],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,creationflags=0x08000000)
        self.reader=threading.Thread(target=self._read,daemon=True); self.reader.start()
        self.err_reader=threading.Thread(target=self._errors,daemon=True); self.err_reader.start()
        if not self.ready.wait(7) or self.error:
            self.close()
            raise RuntimeError('게임 캡처 시작 실패: '+(self.error or '시간 초과')+' / '+' '.join(self.messages))
    def _errors(self):
        import locale
        try:
            for line in iter(self.child.stderr.readline,b''):
                self.messages.append(line.decode(locale.getpreferredencoding(False),errors='replace').strip())
        except (OSError,ValueError): pass
    def _exact(self,n):
        parts=bytearray()
        while len(parts)<n:
            data=self.child.stdout.read(n-len(parts))
            if not data: raise EOFError('게임 종료 또는 캡처 프로세스 중단')
            parts.extend(data)
        return bytes(parts)
    def _read(self):
        try:
            magic,ch,rate=struct.unpack('<4sii',self._exact(12))
            if (magic,ch,rate)!=(b'DS5P',self.channels,48000): raise ValueError('잘못된 게임 캡처 형식')
            self.ready.set()
            while not self.closed:
                size,stamp=struct.unpack('<id',self._exact(12))
                if size<0 or size>48000*self.channels*2 or size%(self.channels*2): raise ValueError('잘못된 캡처 패킷')
                data=self._exact(size)
                with self.lock:
                    if len(self.queue)==self.queue.maxlen: self.drops+=1
                    self.queue.append((stamp,data))
        except Exception as exc:
            if not self.closed: self.error=str(exc)
        finally: self.ready.set()
    def get_read_available(self):
        if self.error or self.child.poll() is not None:
            self.pending.clear()
            raise RuntimeError('게임 전용 캡처 중단: '+(self.error or '종료')+' / '+' '.join(self.messages))
        if self.pending and time.perf_counter()-self.pending_time>.060:
            self.pending.clear(); self.stale+=1
        # Max one capture packet in pending plus one 480-frame read fragment.
        with self.lock:
            while len(self.pending)<480*self.channels*2 and self.queue:
                stamp,data=self.queue.popleft()
                if time.perf_counter()-stamp>.060:
                    self.stale+=1; continue
                if not self.pending: self.pending_time=stamp
                self.pending.extend(data)
        return len(self.pending)//(2*self.channels)
    def read(self,n,**kwargs):
        count=n*self.channels*2
        if self.get_read_available()<n: raise RuntimeError('게임 캡처 버퍼 부족')
        data=bytes(self.pending[:count]); del self.pending[:count]
        return data
    def get_input_latency(self): return 0.0 # Not measured; process-mode status marks unknown.
    def stop_stream(self): self.close()
    def close(self):
        if self.closed: return
        self.closed=True
        try:
            self.child.stdin.close()
            self.child.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            self.child.terminate(); self.child.wait(timeout=2)
        finally:
            self.reader.join(timeout=1); self.err_reader.join(timeout=1)
            self.child.stdout.close(); self.child.stderr.close()
        self.pending.clear()
        with self.lock: self.queue.clear()
