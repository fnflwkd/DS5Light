"""Bounded, best-effort task diagnostics; no resident logger thread or file handle."""
import os,threading
from time import perf_counter
from pathlib import Path
from functools import wraps
from datetime import datetime
_LOCK=threading.Lock()
LIMIT=512*1024

def folder():return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'DS5Light'/'logs'
def log(message):
    if not _LOCK.acquire(False):return
    try:
        import msvcrt
        root=folder();root.mkdir(parents=True,exist_ok=True)
        with (root/'remap-log.lock').open('a+b') as lock:
            if lock.seek(0,2)==0:lock.write(b'0');lock.flush()
            lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:return
            try:
                path=root/'remap.log'
                if path.exists() and path.stat().st_size>=LIMIT:
                    older=root/'remap.log.1'
                    if older.exists():os.replace(older,root/'remap.log.2')
                    os.replace(path,older)
                with path.open('a',encoding='utf8') as stream:
                    stream.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} [{os.getpid()}] '+str(message).replace('\n',' ')[:2000]+'\n')
            finally:
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    except Exception:pass  # Diagnostics must never fail an apply, restore, or shutdown.
    finally:_LOCK.release()

def timed(label):
    def decorate(fn):
        @wraps(fn)
        def run(*args,**kwargs):
            start=perf_counter();outcome='완료'
            try:return fn(*args,**kwargs)
            except Exception as exc:
                outcome='실패: '+str(exc);raise
            finally:log(f'{label} · {perf_counter()-start:.3f}초 · {outcome}')
        return run
    return decorate
