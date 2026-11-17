"""Temporary RAM macro-mask lease; durable evidence precedes every change."""
import hashlib,json,os,struct
from pathlib import Path
from driver_state import atomic_json
from remapping import MacroClient
from studio_slots import device_lock
from xbox_source_remap import compile_plan,Unsupported

def folder():return Path(os.environ['LOCALAPPDATA'])/'DS5Light'/'xbox-remap'
def pending():return folder().exists() and any(folder().glob('*.json'))
def identity(profile):return profile.get('index'),profile.get('name')
def layout(snapshot):return snapshot.firmware,identity(snapshot.profile),snapshot.rows,snapshot.ps_shortcut

class Session:
    def __init__(self,path,client,root=None):
        self.path=bytes(path);self.client=client;self.root=Path(root) if root else folder()
        self.file=self.root/(hashlib.sha256(self.path).hexdigest()+'.json');self.lock=None;self.plan=None;self.reason=''
    def acquire(self):
        import msvcrt
        self.root.mkdir(parents=True,exist_ok=True)
        self.lock=self.file.with_suffix('.lock').open('a+b')
        if self.lock.seek(0,2)==0:self.lock.write(b'0');self.lock.flush()
        self.lock.seek(0)
        try:msvcrt.locking(self.lock.fileno(),msvcrt.LK_NBLCK,1)
        except Exception:self.lock.close();self.lock=None;raise RuntimeError('다른 DS5Light가 이 장치의 리맵을 사용 중입니다.')
    def release(self):
        if self.lock is not None:
            import msvcrt
            self.lock.seek(0)
            try:msvcrt.locking(self.lock.fileno(),msvcrt.LK_UNLCK,1)
            finally:self.lock.close();self.lock=None
    def restore(self):
        if not self.file.exists():return
        try:
            saved=json.loads(self.file.read_text(encoding='utf8'))
            if saved['path']!=self.path.hex() or type(saved['mask']) is not int or not 0<=saved['mask']<=0xffffffff or len(saved['rows'])!=32 or any(len(bytes.fromhex(r))!=35 for r in saved['rows']):raise ValueError('invalid journal')
            applied=saved.get('applied_mask',0xffffffff)
            if type(applied) is not int or not 0<=applied<=0xffffffff or applied|saved['mask']!=applied:raise ValueError('invalid applied mask')
            current=self.client.read()
            if current.firmware!=saved['firmware'] or identity(current.profile)!=tuple(saved['profile']) or [r.hex() for r in current.rows]!=saved['rows'] or current.ps_shortcut!=saved['ps']:
                raise RuntimeError('프로필/리맵이 변경되어 자동 복원하지 않았습니다. 기존 복구 기록을 보존했습니다.')
            if current.disabled not in (saved['mask'],applied):raise RuntimeError('리맵 활성 상태가 외부에서 변경되어 복원을 중단했습니다.')
            if current.disabled!=saved['mask']:
                self.client.studio.control_packet(1,0x6c,struct.pack('<I',saved['mask']))
                verified=self.client.read()
                if verified.disabled!=saved['mask'] or layout(verified)!=layout(current):raise RuntimeError('리맵 복원 확인 실패')
            self.file.unlink()
        except Exception as exc:raise RuntimeError('Pico 리맵 복구 필요: '+str(exc)) from exc
    def begin(self):
        self.acquire()
        with device_lock():
            self.restore()
            original=self.client.read()
            self.plan=None;self.reason=''
            try:self.plan=compile_plan(original)
            except Unsupported as exc:self.reason=str(exc);return None
            applied=0xffffffff & ~self.plan.retained
            if original.disabled==applied:return self.plan
            atomic_json(self.file,dict(path=self.path.hex(),firmware=original.firmware,profile=identity(original.profile),mask=original.disabled,applied_mask=applied,ps=original.ps_shortcut,rows=[r.hex() for r in original.rows]))
            try:
                if self.client.read()!=original:raise RuntimeError('전환 직전 리맵이 바뀌었습니다. Xbox 시작을 중단합니다.')
            except Exception:
                # No device write was attempted; this newly created journal owns no change.
                self.file.unlink()
                raise
            self.client.studio.control_packet(1,0x6c,struct.pack('<I',applied))
            changed=self.client.read()
            if changed.disabled!=applied or layout(changed)!=layout(original):raise RuntimeError('원본 입력 전환 확인 실패')
            return self.plan
    def close(self):
        if self.lock is None:return
        try:
            with device_lock():self.restore()
        finally:self.release()

def recover(path):
    import hid
    device=hid.device();session=None
    try:
        device.open_path(path);session=Session(path,MacroClient(device));session.acquire()
        with device_lock():session.restore()
    finally:
        if session:session.release()
        device.close()

def recover_all():
    if not folder().exists():return
    errors=[]
    for file in sorted(folder().glob('*.json')):
        try:
            path=bytes.fromhex(json.loads(file.read_text(encoding='utf8'))['path'])
            if not path or file.stem!=hashlib.sha256(path).hexdigest():raise ValueError('기록의 장치 경로/파일 이름 불일치')
            recover(path)
        except Exception as exc:errors.append(file.name+': '+str(exc))
    if errors:raise RuntimeError('일부 장치의 리맵 복구가 남아 있습니다: '+' · '.join(errors))
