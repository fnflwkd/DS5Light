"""Explicit temporary native remaps: RAM only, durable backup, verified restore."""
import os,json,hashlib
from pathlib import Path
from dataclasses import replace
from driver_state import atomic_json
from remapping import Snapshot,device_operation,PreflightChanged
from remap_diagnostics import timed
_owners={}
def folder():return Path(os.environ['LOCALAPPDATA'])/'DS5Light'/'temporary-remap'
def path_for(path):return folder()/(hashlib.sha256(bytes(path)).hexdigest()+'.json')
def pending(path=None):
    if path is not None:return path_for(path).exists()
    return folder().exists() and any(folder().glob('*.json'))
def pack(s):return dict(firmware=s.firmware,profile=s.profile,disabled=s.disabled,ps_shortcut=s.ps_shortcut,rows=[r.hex() for r in s.rows])
def unpack(d):
    s=Snapshot(d['firmware'],d['profile'],d['disabled'],d['ps_shortcut'],tuple(bytes.fromhex(r) for r in d['rows']))
    if len(s.rows)!=32 or any(len(r)!=35 for r in s.rows) or type(s.disabled) is not int or not 0<=s.disabled<=0xffffffff or s.ps_shortcut not in (0,1):raise ValueError('임시 리맵 복구 기록 손상')
    return s

def same(a,b):
    from xbox_remap_session import layout
    return layout(a)==layout(b) and a.disabled==b.disabled

def acquire(path):
    path=bytes(path)
    if path not in _owners:
        from xbox_remap_session import Session
        lease=Session(path,None,folder());lease.acquire();_owners[path]=lease

def release(path):
    lease=_owners.pop(bytes(path),None)
    if lease:lease.release()

def load(path):
    data=json.loads(path_for(path).read_text(encoding='utf8'))
    if data['path']!=bytes(path).hex():raise ValueError('임시 복구 장치 경로 불일치')
    if data.get('phase','temporary') not in ('temporary','saving','committed','restoring'):raise ValueError('임시 복구 단계 오류')
    for key in ('original','previous','expected'):unpack(data[key])
    return data

def apply_recorded(path,record,operation):
    """Persist intent before writes; undo intent only for a proven no-write abort."""
    file=path_for(path)
    previous=load(path) if file.exists() else None
    atomic_json(file,record)
    try:return operation()
    except PreflightChanged:
        if previous is not None:atomic_json(file,previous)
        else:file.unlink();release(path)
        raise

@timed("임시 적용")
def temporary(c,path,original,rows,mask,backup,ps_enabled=None,*,allow_edited=False):
    acquire(path);file=path_for(path)
    old=load(path) if file.exists() else None
    if old and old.get('phase')=='restoring':raise RuntimeError('이전 복원이 남아 있습니다. 임시 설정 되돌리기를 먼저 완료하세요.')
    if old and old.get('phase') in ('saving','committed'):raise RuntimeError('Pico 저장 결과 확인이 남아 있습니다. 임시 적용 대신 Pico에 저장을 다시 시도하세요.')
    if old and not any(same(original,unpack(old[k])) for k in ('original','previous','expected')):raise RuntimeError('임시 적용 후 장치 설정이 바뀌었습니다. 복구 기록을 보존합니다.')
    expected=replace(original,rows=tuple(rows),disabled=mask,ps_shortcut=original.ps_shortcut if ps_enabled is None else int(ps_enabled))
    if ps_enabled:
        from ps_policy import ps_rows
        expected=replace(expected,disabled=expected.disabled|ps_rows(rows))
    record=dict(path=bytes(path).hex(),original=old['original'] if old else pack(original),previous=pack(original),expected=pack(expected))
    return apply_recorded(path,record,lambda:c.apply(original,rows,mask,False,backup,ps_enabled=ps_enabled,persist=False,allow_edited=allow_edited,backup=False))

def known_partial(current,previous,expected):
    from xbox_remap_session import identity
    from ps_policy import ps_rows
    return (current.firmware==previous.firmware==expected.firmware
        and identity(current.profile)==identity(previous.profile)==identity(expected.profile)
        and current.ps_shortcut in (previous.ps_shortcut,expected.ps_shortcut)
        and current.disabled in (previous.disabled,expected.disabled,previous.disabled|ps_rows(expected.rows))
        and all(row in (old,new) for row,old,new in zip(current.rows,previous.rows,expected.rows)))

@timed("Pico에 저장")
def saved(c,path,original,rows,mask,disable_ps,backup,ps_enabled=None,*,allow_edited=False):
    file=path_for(path)
    acquire(path)
    record=load(path) if file.exists() else dict(path=bytes(path).hex(),original=pack(original),previous=pack(original),expected=pack(original))
    if record.get('phase')=='restoring':raise RuntimeError('이전 복원이 남아 있습니다. 임시 설정 되돌리기를 먼저 완료하세요.')
    from ps_policy import resolve,ps_rows
    target_ps=resolve(original.ps_shortcut,disable_ps,ps_enabled)
    expected=replace(original,rows=tuple(rows),disabled=mask|(ps_rows(rows) if ps_enabled is True else 0),ps_shortcut=target_ps)
    known=any(same(original,unpack(record[k])) for k in ('original','previous','expected'))
    retry=(record.get('phase')=='saving' and same(expected,unpack(record['expected'])) and known_partial(original,unpack(record['previous']),unpack(record['expected'])))
    if not known and not retry:raise RuntimeError('기록한 저장 범위 밖의 변경입니다. 자동 덮어쓰기를 중단했습니다. 기존 복구 기록을 확인하세요.')
    if record.get('phase')=='committed' and same(original,expected) and same(expected,unpack(record['expected'])):
        current=c.read()
        if not same(current,original):raise RuntimeError('저장 결과 확인 중 장치 설정이 바뀌었습니다.')
        file.unlink();release(path);return current
    record.update(phase='saving',previous=pack(original),expected=pack(expected))
    result=apply_recorded(path,record,lambda:c.apply(original,rows,mask,disable_ps,backup,ps_enabled=ps_enabled,force_save=True,allow_edited=allow_edited))
    # Commit success must survive a subsequent failure to delete the journal.
    record.update(phase='committed',original=pack(result),previous=pack(result),expected=pack(result))
    atomic_json(file,record)
    file.unlink();release(path);return result

@timed("임시 설정 복원")
def restore(c,path):
    file=path_for(path)
    if not file.exists():return c.read()
    acquire(path);data=load(path)
    if data.get('phase')=='saving':raise RuntimeError('Pico 저장 완료 여부가 미확정입니다. 자동 복원을 중단했습니다. 설정을 다시 읽고 Pico에 저장을 재시도하세요.')
    current=c.read();original=unpack(data['original'])
    resuming=(data.get('phase','temporary') in ('temporary','restoring') and known_partial(current,unpack(data['previous']),unpack(data['expected'])))
    if not resuming and not any(same(current,unpack(data[k])) for k in ('original','previous','expected')):
        raise RuntimeError('장치 프로필/리맵이 바뀌었거나 적용이 일부만 끝났습니다. 자동 덮어쓰기 없이 임시 복구 기록을 보존했습니다.')
    if not same(current,original):
        data.update(phase='restoring',previous=pack(current),expected=pack(original))
        atomic_json(file,data)
        current=c.apply(current,original.rows,original.disabled,False,folder()/'backups',ps_enabled=bool(original.ps_shortcut),persist=False,backup=False)
        if not same(current,original):raise RuntimeError('임시 리맵 복원 검증 실패')
    file.unlink();release(path);return current

def restore_connected(path):return device_operation(path,lambda c:restore(c,path))
def owned_pending():return any(path_for(p).exists() for p in _owners)
def restore_owned():
    failures=[]
    for path in tuple(_owners):
        if not path_for(path).exists():release(path);continue
        try:restore_connected(path)
        except Exception as exc:failures.append(str(exc))
    if failures:raise RuntimeError(' · '.join(failures))


def retry_saved(c,path,backup):
    acquire(path);record=load(path)
    if record.get('phase') not in ('saving','committed'):raise RuntimeError('재시도할 Pico 저장 기록이 없습니다.')
    expected=unpack(record['expected']);current=c.read()
    return saved(c,path,current,expected.rows,expected.disabled,False,backup,ps_enabled=bool(expected.ps_shortcut))
