"""Small durable state files; no background tasks."""
import json,os,tempfile,subprocess
from pathlib import Path

def atomic_json(path,data,*,allow_nan=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f:
            temp=Path(f.name);json.dump(data,f,ensure_ascii=False,allow_nan=allow_nan);f.flush();os.fsync(f.fileno())
        os.replace(temp,path);temp=None
    finally:
        if temp is not None:temp.unlink(missing_ok=True)

def powershell():
    return str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')

def ps_read(script):
    r=subprocess.run([powershell(),'-NoProfile','-NonInteractive','-Command',
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $ErrorActionPreference='Stop'; "+script],
        capture_output=True,encoding='utf-8',errors='replace',timeout=12,creationflags=0x08000000)
    if r.returncode:raise RuntimeError(r.stderr.strip() or 'Windows 상태 조회 실패')
    return r.stdout.strip()

def boot_id():
    value=ps_read("(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().Ticks")
    if not value.isdigit():raise RuntimeError('Windows 재부팅 상태를 확인하지 못했습니다.')
    return value

class RebootGate:
    def __init__(self,path=None):
        self.path=Path(path) if path else Path(os.environ['LOCALAPPDATA'])/'DS5Light'/'driver-reboot.json'
        self.cached_boot=None
    def current(self):
        if self.cached_boot is None:self.cached_boot=boot_id()
        return self.cached_boot
    def ensure(self):
        if not self.path.exists():return
        try:data=json.loads(self.path.read_text(encoding='utf8'));old=data['boot']
        except Exception as exc:raise RuntimeError('재부팅 기록 확인 실패 · 진단 로그를 확인하세요.') from exc
        if not isinstance(old,str) or not old.isdigit():raise RuntimeError('재부팅 기록 형식 오류')
        if self.current()==old:raise RuntimeError('드라이버 변경 후 Windows 재부팅이 필요합니다. 앱만 다시 켜서는 해제되지 않습니다.')
        self.path.unlink()
    def mark(self):atomic_json(self.path,dict(boot=self.current()))


def prune_xbox_logs(directory,current,keep=30):
    """Bound only our UUID logs; never touch user-selected or installer logs."""
    import re
    directory=Path(directory);current=Path(current)
    owned=[p for p in directory.iterdir() if p.is_file() and re.fullmatch(r'xbox-[0-9a-f]{32}(?:\.previous)?\.log',p.name)]
    others=sorted((p for p in owned if p!=current),key=lambda p:p.stat().st_mtime,reverse=True)
    for p in others[max(0,keep-1):]:p.unlink()
