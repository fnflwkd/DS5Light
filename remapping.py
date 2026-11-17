from studio_slots import device_lock
"""
Studio 1.42.0 macro editor. Protocol reference: SOURCES.md.

No input polling, key injection, firmware updates or global configuration saves.
Definitions are global; the enable mask and PS shortcut change in RAM only.
"""
from ps_policy import ps_rows,resolve,write_policy
from dataclasses import dataclass,replace
from datetime import datetime, timezone
import json
import struct
from pathlib import Path
from studio_slots import StudioClient, _DEVICE_LOCK,response_waits
from remap_diagnostics import timed

BUTTONS = ('↑','↓','←','→','□','×','○','△','L1','R1','L2','R2',
           'Create','Options','L3','R3','PS','Touchpad','Mute')
OUTPUTS = ('Keyboard','×','○','□','△','L1','R1','L3','R3','L2','R2',
           'Mouse left','Mouse right','Mouse middle','Wheel up','Wheel down',
           'Create','Options','Touchpad','↑','↓','←','→')
KEYS = {chr(65+i):4+i for i in range(26)}
KEYS.update({str((i+1)%10):30+i for i in range(10)})
KEYS.update({f'F{i+1}':58+i for i in range(12)})
KEYS.update({f'F{i+13}':104+i for i in range(12)})
KEYS.update({f'NUM{i}':88+i for i in range(1,10)})
KEYS.update(NUM0=98,NUMDECIMAL=99,NUMDIVIDE=84,NUMMULTIPLY=85,
            NUMSUBTRACT=86,NUMADD=87,NUMENTER=88)
KEYS.update(dict(ENTER=40,ESC=41,BACKSPACE=42,TAB=43,SPACE=44,MINUS=45,
                 EQUAL=46,LEFTBRACKET=47,RIGHTBRACKET=48,BACKSLASH=49,
                 SEMICOLON=51,QUOTE=52,GRAVE=53,COMMA=54,PERIOD=55,SLASH=56,
                 CAPSLOCK=57,PRINTSCREEN=70,SCROLLLOCK=71,PAUSE=72,INSERT=73,
                 HOME=74,PAGEUP=75,DELETE=76,END=77,PAGEDOWN=78,RIGHT=79,
                 LEFT=80,DOWN=81,UP=82,NUMLOCK=83,
                 CTRL=224,SHIFT=225,ALT=226,WIN=227,RCTRL=228,RSHIFT=229,
                 RALT=230,RWIN=231))
EMPTY = bytes(35)
SWIPE_DIRECTIONS = ('위로','아래로','왼쪽으로','오른쪽으로')

def is_swipe(raw):
    return len(raw)==35 and 0x80<=raw[4]<=0x8f and not any(raw[:4]) and raw[5]==0

def make_swipe(direction, right, two, output, keys=''):
    if type(direction) is not int or not 0<=direction<4:raise ValueError('스와이프 방향을 선택하세요.')
    raw=bytearray(make_record(1,output,keys,hold=False,replace=False))
    raw[:4]=bytes(4);raw[4]=0x80|direction|(4 if right else 0)|(8 if two else 0)
    return bytes(raw)

def easy_swipe(rows,disabled,direction,output,keys):
    """One direction from either half, with either finger count; atomic staging."""
    result=list(rows)
    for zone in (False,True):
        for two in (False,True):
            record=make_swipe(direction,zone,two,output,keys)
            matches=[i for i,r in enumerate(result) if is_swipe(r) and r[4]==record[4]]
            if len(matches)>1:raise ValueError('같은 스와이프가 여러 개입니다. 고급 설정에서 정리하세요.')
            index=matches[0] if matches else next((i for i,r in enumerate(result) if r==EMPTY),None)
            if index is None:raise ValueError('쉬운 스와이프는 방향마다 4칸이 필요합니다. 설정 목록에 빈칸을 확보하세요.')
            if not editable(result[index]):raise ValueError('기존 고급 스와이프를 덮어쓸 수 없습니다.')
            result[index]=record[:19]+result[index][19:35];disabled&=~(1<<index)
    return result,disabled

def parse_keys(text):
    names = [s.strip().upper() for s in text.split('+') if s.strip()]
    if not 1 <= len(names) <= 4 or len(set(names)) != len(names):
        raise ValueError('키보드 조합은 수정키 포함 서로 다른 1~4키입니다.')
    try:return bytes([KEYS[n] for n in names]).ljust(4,b'\0')
    except KeyError as e:raise ValueError(f'지원하지 않는 키: {e.args[0]}') from e

def keys_text(raw):
    inverse={v:k for k,v in KEYS.items()}
    return '+'.join(inverse.get(k,f'[{k}]') for k in raw if k)

def editable(raw):
    return (len(raw)==35 and ((raw[4]==0 and raw[5] in (0,2,6)) or is_swipe(raw))
            and (raw[17]!=0 or raw[5]&2 or raw[11] in (0,0x1b))
            and not any(raw[12:17]) and raw[18]==0 and raw[17]<len(OUTPUTS)
            and not (int.from_bytes(raw[:4],'little') >> len(BUTTONS))
            and all(k==0 or k in KEYS.values() for k in raw[7:11]))

def make_record(chord, output, keys='', hold=True, replace=True, label=''):
    if not 0 < chord < (1 << len(BUTTONS)):raise ValueError('입력 버튼을 선택하세요.')
    if output not in OUTPUTS:raise ValueError('지원하지 않는 출력입니다.')
    if replace and not hold:raise ValueError('원본 입력 교체는 유지 방식에서 지원합니다.')
    raw=bytearray(35);raw[:4]=struct.pack('<I',chord)
    raw[5]=(2 if hold else 0)|(4 if replace else 0)
    if output=='Keyboard':raw[7:11]=parse_keys(keys)
    raw[11]=0x1b  # release positions 3,2,1,0; modifiers release last
    raw[17]=OUTPUTS.index(output)
    try:data=label.encode('ascii')
    except UnicodeEncodeError as e:raise ValueError('이름은 영문·숫자로 입력하세요.') from e
    if len(data)>16:raise ValueError('이름은 영문/숫자 16바이트까지입니다.')
    raw[19:19+len(data)]=data
    return bytes(raw)

def describe(raw):
    if raw==EMPTY:return '—','—'
    if not editable(raw):return '기존 고급 매크로 (보존)','Studio에서 편집'
    chord=int.from_bytes(raw[:4],'little')
    if is_swipe(raw):
        return ('스와이프 '+SWIPE_DIRECTIONS[raw[4]&3]+' · '+('오른쪽' if raw[4]&4 else '왼쪽')+' 시작 · '+('두 손가락' if raw[4]&8 else '한 손가락'),keys_text(raw[7:11]) if raw[17]==0 else OUTPUTS[raw[17]])
    return '+'.join(n for i,n in enumerate(BUTTONS) if chord & (1<<i)), (keys_text(raw[7:11]) if raw[17]==0 else OUTPUTS[raw[17]])

@dataclass(frozen=True)
class Snapshot:
    firmware: str
    profile: dict
    disabled: int
    ps_shortcut: int
    rows: tuple

class PreflightChanged(RuntimeError):
    """Fresh baseline rejected or unavailable; apply issued no setting writes."""

class MacroClient:
    def __init__(self,device,valid=lambda:True,sleep=None):
        self.device=device;self.valid=valid
        self.studio=StudioClient(device) if sleep is None else StudioClient(device,sleep)
    def check(self):
        if not self.valid():raise RuntimeError('작업 취소 · 다시 읽어 현재 상태를 확인하세요.')
    def packet(self,command,index=None,record=b''):
        self.check()
        if command not in (0x17,0x18,0x19):raise ValueError('Unsupported macro command')
        if command!=0x19 and (type(index) is not int or not 0<=index<32):raise ValueError('Invalid row')
        if command==0x18 and len(record)!=35:raise ValueError('Invalid record')
        packet=bytes([0x80,0x66,command])+(bytes([index]) if index is not None else b'')+record
        if self.device.send_feature_report(packet.ljust(64,b'\0'))!=64:raise RuntimeError('Macro write failed')
        for delay in response_waits(10, command==0x17):
            self.check();self.studio.sleep(delay)
            try:raw=bytes(self.device.get_feature_report(0x84,64))
            except OSError:
                if command==0x17:continue  # Retry only reception within the same budget.
                raise
            if len(raw)<5 or raw[:3]!=bytes([0x84,0x66,command]):continue
            if raw[3]==0xfe:continue
            if index is not None and raw[4]!=index:continue
            if raw[3]!=0:raise RuntimeError('Studio rejected macro command')
            if command==0x17:
                if len(raw)<40:raise RuntimeError('Truncated macro record')
                return raw[5:40]
            return
        raise TimeoutError('매크로 응답 없음 · 적용 결과 미확정. 다른 Studio 앱을 닫고 다시 읽으세요.')
    def field(self,field):
        self.check();return self.studio.control_packet(4,field)
    @timed("리맵 전체 읽기")
    def read(self):
        self.check();version=self.studio.firmware()
        if version!='1.42.0':raise ValueError(f'검증된 편집 형식은 Studio 1.42.0입니다. 현재: {version}')
        before=self.studio.profile()
        disabled=int.from_bytes(self.field(0x6c)[4:8],'little');ps=self.field(0x0e)[4]
        rows=tuple(self.packet(0x17,i) for i in range(32))
        after=self.studio.profile()
        if before!=after or disabled!=int.from_bytes(self.field(0x6c)[4:8],'little') or ps!=self.field(0x0e)[4]:
            raise RuntimeError('조회 중 프로필/설정 변경 · 다시 읽으세요.')
        return Snapshot(version,after,disabled,ps,rows)
    @timed("리맵 적용·검증")
    def apply(self,original,rows,disabled,disable_ps,backup_dir,*,ps_enabled=None,persist=True,force_save=False,allow_edited=False,backup=True):
        rows=tuple(rows)
        target_ps=resolve(original.ps_shortcut,disable_ps,ps_enabled)
        if ps_enabled is True:disabled|=ps_rows(rows)
        if len(rows)!=32 or any(len(r)!=35 for r in rows) or not 0<=disabled<=0xffffffff:raise ValueError('Invalid macro table')
        changed=[i for i in range(32) if rows[i]!=original.rows[i]]
        for i in changed:
            if not editable(original.rows[i]) or not editable(rows[i]):raise ValueError('고급 매크로는 보존해야 합니다.')
        active=[r for i,r in enumerate(rows) if not disabled&(1<<i) and r!=EMPTY]
        newly_active=[i for i,r in enumerate(rows) if not disabled&(1<<i) and
                      (r!=original.rows[i] or original.disabled&(1<<i))]
        for i in newly_active:
            if rows[i]==EMPTY:raise ValueError('빈 행은 활성화할 수 없습니다.')
            for j,r in enumerate(rows):
                if i!=j and not disabled&(1<<j) and r[:6]==rows[i][:6]:
                    from pad_combo import valid_group
                    group=[x for k,x in enumerate(rows) if not disabled&(1<<k) and x[:6]==rows[i][:6]]
                    if not valid_group(group):raise ValueError(f'{i+1}행과 {j+1}행의 입력/방식이 겹칩니다.')
        if any(int.from_bytes(r[:4],'little')&(1<<16) for r in active) and target_ps:
            raise ValueError('PS 입력 충돌: Studio PS 단축키 사용을 해제하세요.')
        try:current=self.read()
        except Exception as exc:
            raise PreflightChanged('쓰기 전 설정 확인 실패 · 장치에 쓰지 않았습니다: '+str(exc)) from exc
        if allow_edited:
            # Xbox mask restoration can change only this metadata bit.
            profile=dict(original.profile)
            if 'edited' in current.profile:profile['edited']=current.profile['edited']
            original=replace(original,profile=profile)
        if current!=original:
            differences=[]
            if current.firmware!=original.firmware:differences.append('펌웨어')
            if current.profile!=original.profile:differences.append('프로필 '+str(original.profile)+' → '+str(current.profile))
            if current.disabled!=original.disabled:differences.append(f'활성 상태 {original.disabled:08x} → {current.disabled:08x}')
            if current.ps_shortcut!=original.ps_shortcut:differences.append(f'PS 단축키 {original.ps_shortcut} → {current.ps_shortcut}')
            rows_changed=[str(i+1) for i,(a,b) in enumerate(zip(original.rows,current.rows)) if a!=b]
            if rows_changed:differences.append('리맵 행 '+', '.join(rows_changed))
            raise PreflightChanged('장치 설정이 변경되었습니다. 다시 읽은 뒤 편집하세요. 장치에 쓰지 않았습니다. 차이: '+' / '.join(differences))
        if not changed and disabled==original.disabled and target_ps==original.ps_shortcut and not force_save:
            return current
        if backup:
            folder=Path(backup_dir);folder.mkdir(parents=True,exist_ok=True)
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            (folder/f'macros-{stamp}.json').write_text(json.dumps(dict(firmware=original.firmware,profile=original.profile,
                disabled=original.disabled,ps_shortcut=original.ps_shortcut,rows=[r.hex() for r in original.rows]),indent=2),encoding='utf-8')
        def check_profile():
            self.check();current=self.studio.profile()
            if (current['index'],current['name'])!=(original.profile['index'],original.profile['name']):
                raise RuntimeError('적용 중 프로필 변경 · 추가 쓰기를 중단했습니다. 다시 읽으세요.')
        # Protect PS policy before replacing definitions in already-enabled rows.
        policy_mask=original.disabled;policy_ps=original.ps_shortcut
        if policy_ps and not target_ps:
            write_policy(self,check_profile,policy_mask,policy_mask,policy_ps,target_ps)
            policy_ps=target_ps
        elif target_ps:
            protected=policy_mask | ps_rows(rows)
            write_policy(self,check_profile,policy_mask,protected,policy_ps,policy_ps)
            policy_mask=protected
        # No automatic retries or rollback after an uncertain write.
        for i in changed:
            check_profile()
            self.packet(0x18,i,rows[i])
            if self.packet(0x17,i)!=rows[i]:raise RuntimeError('RAM 매크로 검증 실패 · 다시 읽으세요.')
        if persist and (changed or force_save):
            check_profile();self.packet(0x19)
        write_policy(self,check_profile,policy_mask,disabled,policy_ps,target_ps)
        result=self.read()
        check_profile()
        if (result.profile['index'],result.profile['name'])!=(original.profile['index'],original.profile['name']):raise RuntimeError('적용 후 프로필 변경 · 결과 미확인')
        if result.rows!=rows or result.disabled!=disabled or result.ps_shortcut!=target_ps:
            raise RuntimeError('적용 후 검증 실패 · 다시 읽고 백업을 확인하세요.')
        return result
    def reconnect_usb(self,expected):
        if self.read()!=expected:raise RuntimeError('설정이 바뀌어 USB 연결을 다시 시작하지 않았습니다. 다시 읽으세요.')
        self.check()
        if self.device.send_feature_report(bytes([0x80,0x66,0x03])+bytes(61))!=64:
            raise RuntimeError('USB 재인식 명령 결과 미확정 · 다시 읽어 주세요.')

def device_operation(path,operation,valid=lambda:True):
    import hid
    with device_lock():
        if not valid():raise RuntimeError('작업 취소')
        device=hid.device()
        try:
            device.open_path(path)
            return operation(MacroClient(device,valid))
        finally:device.close()
