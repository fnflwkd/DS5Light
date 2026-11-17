"""Windows per-process loopback helper transport. Fail closed, never full-system fallback."""
import struct
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from cleanup_utils import recover_owners,cleanup_failed_start

HELPER=Path(__file__).with_name('ProcessCapture.exe')

_PENDING=set()  # Keep failed startup/teardown owners available for retry.

def recover_pending():
    return recover_owners(_PENDING)

class ProcessCaptureStream:
    def __init__(self,pid,channels=6):
        if channels not in (2,6,8): raise ValueError('게임 캡처 채널은 2, 6 또는 8')
        recover_pending()
        self.cleanup_complete=False
        self.pid,self.channels=pid,channels
        self.closed=False; self.error=None; self.ready=threading.Event()
        self.lock=threading.Lock(); self.queue=deque(maxlen=8); self.pending=bytearray()
        self.pending_time=0.0
        self.drops=0; self.stale=0; self.messages=deque(maxlen=12)
        self.child=subprocess.Popen([str(HELPER),str(pid),str(channels)],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,creationflags=0x08000000)
        self.reader=None;self.err_reader=None
        try:
            self.reader=threading.Thread(target=self._read,daemon=True); self.reader.start()
            self.err_reader=threading.Thread(target=self._errors,daemon=True); self.err_reader.start()
            if not self.ready.wait(7) or self.error:
                raise RuntimeError('게임 캡처 시작 실패: '+(self.error or '시간 초과')+' / '+' '.join(self.messages))
        except Exception as exc:
            cleanup_failed_start(self,exc);raise
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
        if getattr(self,'cleanup_complete',False):return
        self.closed=True  # Stop producing data; this does not mean cleanup finished.
        _PENDING.add(self)
        try:
            try:self.child.stdin.close()
            except (OSError,ValueError):pass
            try:self.child.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                self.child.terminate();self.child.wait(timeout=2)
            for reader in (self.reader,self.err_reader):
                if reader is not None and reader.ident is not None:
                    reader.join(timeout=1)
                    if reader.is_alive():raise RuntimeError('게임 캡처 읽기 스레드 종료 미확인')
            self.child.stdout.close();self.child.stderr.close()
            self.pending.clear()
            with self.lock:self.queue.clear()
        except Exception as exc:
            raise RuntimeError('게임 캡처 종료 미확인 · 다시 시작하면 정리를 재시도합니다: '+str(exc)) from exc
        self.cleanup_complete=True
        _PENDING.discard(self)
