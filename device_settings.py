"""On-demand controls for the audited original Studio 1.42 protocol."""
import json
import math
import time
from safe_notify import notify
import struct
import os
from pathlib import Path
from datetime import datetime,timezone
from common_remap import CommonRemap

OPTIONS={'polling':(9,0,2),'idle_minutes':(6,5,60),'never_disconnect':(7,0,1)}

def read_options(c):
    before=c.studio.profile();values={};errors={}
    for key,(field,low,high) in OPTIONS.items():
        try:
            c.check();value=c.field(field)[4]
            if not low<=value<=high:raise ValueError('지원하지 않는 설정값')
            values[key]=value
        except Exception as exc:errors[key]=str(exc)
    c.check();after=c.studio.profile()
    if before!=after:raise RuntimeError('조회 중 프로필 변경 · 다시 조회하세요.')
    return dict(profile=after,values=values,errors=errors,firmware=c.studio.firmware())

def set_option(c,expected,key,value):
    if key not in OPTIONS:raise ValueError('지원하지 않는 설정')
    field,low,high=OPTIONS[key]
    if type(value) is not int or not low<=value<=high:raise ValueError('설정값 범위 오류')
    if c.studio.firmware()!='1.42.0':raise ValueError('설정 쓰기는 검토된 원본 Studio 1.42.0에서 지원합니다.')
    before=read_options(c)
    if before['profile']!=expected or key not in before['values']:raise RuntimeError('장치 상태 변경 또는 조회 실패 · 다시 조회하세요.')
    if before['values'][key]!=value:
        c.check()
        if c.studio.profile()!=expected:raise RuntimeError('전송 직전 프로필 변경 · 쓰지 않았습니다.')
        c.check();c.studio.control_packet(1,field,bytes([value]))
    after=read_options(c)
    if after['profile']['index']!=expected['index'] or after['profile']['name']!=expected['name'] or after['values'].get(key)!=value:
        raise RuntimeError('적용 결과 미확인 · 다시 조회하세요. 명령은 재전송하지 않았습니다.')
    return after

def encode_settings(changes):
    result={}
    for key,value in changes.items():
        if key=='gain':
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 1<=value<=2:raise ValueError('전체 강도 범위 오류')
            result[key]=(1,struct.pack('<f',value))
        else:
            limits=dict(OPTIONS,intensity=(0x13,0,200),trigger=(0xc0,0,10))
            if key not in limits:raise ValueError('지원하지 않는 저장 설정')
            field,low,high=limits[key]
            if type(value) is not int or not low<=value<=high:raise ValueError('설정값 범위 오류: '+key)
            result[key]=(field,bytes([value]))
    return result

def save_current(c,expected,folder,progress=lambda message:None,changes=None,*,path=None):
    from temporary_remap import pending
    if pending(path):raise RuntimeError('임시 리맵을 복원하거나 Pico에 저장한 뒤 프로필을 저장하세요.')
    changes=dict(changes or {});encoded=encode_settings(changes)
    if c.studio.firmware()!='1.42.0':raise ValueError('프로필 저장은 검토된 원본 Studio 1.42.0에서 지원합니다.')
    index=expected.get('index') if expected else None
    if type(index) is not int or not 0<=index<32:raise ValueError('현재 저장 슬롯을 먼저 확인하세요.')
    if c.studio.profile()!=expected:raise RuntimeError('현재 프로필이 변경되었습니다. 다시 조회하세요.')
    timings=[];overall=0;last_message=None
    original_progress=progress
    def progress(text):
        nonlocal last_message
        message=f'전체 {overall}% · '+text
        if message!=last_message:notify(original_progress,message);last_message=message
    def stage(value,text):
        nonlocal overall
        overall=max(overall,value);progress(text)
    reader=CommonRemap(c)
    def measured(label,fn):
        started=time.monotonic()
        try:return fn()
        finally:
            elapsed=time.monotonic()-started;timings.append((label,elapsed))
            progress(f'{label} · {elapsed:.2f}초')
    def ensure_profile():
        c.check();profile=c.studio.profile()
        if (profile['index'],profile['name'])!=(expected['index'],expected['name']):raise RuntimeError('현재 프로필 변경 감지 · 작업 중단')
        c.check()
    def read_body(slot,low,high,label):
        stage(low,label)
        if slot is None:ensure_profile()
        result=measured(label,lambda:reader.body(slot,progress=lambda done,total:stage(low+(high-low)*done//total,label)))
        if slot is None:ensure_profile()
        return result
    info=reader.info(index)
    if not info['valid'] or info['version']!=19:raise ValueError('현재 슬롯의 저장 형식을 확인할 수 없습니다.')
    progress('현재 슬롯 원본 백업 읽는 중')
    old=read_body(index,0,18,'1/7 저장 슬롯 백업 읽기');current=read_body(None,18,36,'2/7 현재 설정 백업 읽기')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    backup=folder/('profile-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    with backup.open('x',encoding='utf-8') as stream:
        json.dump(dict(profile=expected,slot=info,saved=old,current=current),stream,ensure_ascii=False,indent=2)
        stream.flush();os.fsync(stream.fileno())
    progress('백업 완료: '+str(backup))
    if c.studio.profile()!=expected or reader.info(index)!=info or read_body(index,36,54,'3/7 저장 슬롯 변경 여부 확인')!=old:
        raise RuntimeError('백업 이후 설정 변경 감지 · 저장하지 않았습니다. 백업: '+str(backup))
    try:
        stage(54,'4/7 화면 설정 적용')
        for key,(field,payload) in encoded.items():
            ensure_profile()
            expected_field=bytes.fromhex(current['fields'][str(field)])
            if reader.field(None,field)!=expected_field:raise RuntimeError('적용할 설정이 외부에서 변경됨: '+key)
            if expected_field[:len(payload)]==payload:continue
            labels=dict(polling='폴링레이트',idle_minutes='연결 해제 대기시간',never_disconnect='자동 연결 해제 안 함',gain='전체 강도',intensity='오디오햅틱 강도',trigger='트리거 강도 감소')
            progress('화면 설정 적용 중: '+labels[key]);ensure_profile()
            c.studio.control_packet(1,field,payload)
            actual=reader.field(None,field)
            if actual[:len(payload)]!=payload:raise RuntimeError('화면 설정 적용 결과 불일치: '+key)
            current['fields'][str(field)]=actual.hex()
        if read_body(None,56,74,'5/7 저장 전 전체 설정 확인')!=current:raise RuntimeError('설정 적용 중 다른 값이 변경됨')
        # reader.save validates the profile again immediately before the command.
        stage(74,'6/7 현재 프로필에 저장 중 · 전원과 USB 연결을 유지하세요.')
        measured('프로필 저장 명령',lambda:reader.save(info))  # Exactly one command; raw 16-byte name is preserved.
        progress('저장된 슬롯 내용을 다시 읽어 검증 중')
        if reader.info(index)!=info or read_body(index,80,99,'7/7 저장 결과 전체 확인')!=current:raise RuntimeError('저장된 설정 내용 불일치')
        after=c.studio.profile()
        if after['index']!=index or after['name']!=expected['name'] or after['edited']:raise RuntimeError('현재 프로필 상태 불일치')
        stage(100,'프로필 저장 및 재조회 검증 완료')
        return dict(profile=after,settings=changes,backup=str(backup),timings=timings,message='현재 프로필 저장 및 재조회 검증 완료 · 전원 재연결 후 지속성은 별도 확인하세요.')
    except Exception as exc:raise RuntimeError('저장 결과 미확인 · 자동 재시도하지 않았습니다. '+str(exc)+' · 백업: '+str(backup)) from exc
