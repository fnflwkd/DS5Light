"""Explicit, one-time common mapping save for Studio 1.42.0 (config v19).

No resident watcher. Slot activation loads the entire saved body; only macro
mask/explicit PS shortcut consent are changed. Compare readable fields and
custom trigger arrays before saving, then verify the stored result.
"""
from studio_slots import response_waits
from ps_policy import ps_rows,resolve,write_policy
import json
import os
from pathlib import Path
from datetime import datetime,timezone
from common_remap_fields import FIELDS

class CommonRemap:
    def __init__(self,client,progress=lambda text:None):self.c=client;self.progress=progress
    def packet(self,command,payload=b'',echo=b''):
        if command not in (0x0a,0x0d,0x15,0x12,9,8):raise ValueError('Unsupported common mapping command')
        self.c.check()
        packet=(bytes([0x80,0x66,command])+payload).ljust(64,b'\0')
        if len(packet)!=64 or self.c.device.send_feature_report(packet)!=64:raise RuntimeError('프로필 명령 전송 결과 미확정')
        for delay in response_waits(30, command in (0x0a,0x0d,0x15,0x12)):
            self.c.check();self.c.studio.sleep(delay)
            try:raw=bytes(self.c.device.get_feature_report(0x84,64))
            except OSError:
                if command in (0x0a,0x0d,0x15,0x12):continue
                raise
            if len(raw)!=64 or raw[:3]!=bytes([0x84,0x66,command]) or raw[3]==0xfe:continue
            if raw[4:4+len(echo)]!=echo:continue
            if raw[3]!=0:raise RuntimeError(f'프로필 명령 {command:02x} 실패/저장 미확정 ({raw[3]})')
            return raw
        raise TimeoutError('프로필 응답 없음 · 명령을 재전송하지 않았습니다.')
    def info(self,index):
        raw=self.packet(0x0a,bytes([index]),bytes([index]))
        if raw[5] not in (0,1):raise ValueError('잘못된 프로필 정보')
        return dict(index=index,valid=bool(raw[5]),version=raw[6],name=raw[7:23].hex())
    def field(self,index,fid):
        if index is None:
            raw=self.c.field(fid)
            if len(raw)!=64:raise RuntimeError('잘린 설정 응답 · 저장 중단')
            return bytes(raw[4:12])
        return self.packet(0x0d,bytes([index,fid]),bytes([index,fid]))[6:14]
    def body(self,index,progress=None):
        fields={};total=len(FIELDS)+10
        for number,fid in enumerate(FIELDS):
            fields[str(fid)]=self.field(index,fid).hex()
            if progress is not None and (number%25==0 or number+1==len(FIELDS)):progress(number+1,total)
            if progress is None and number%25==0:self.progress(f'공통 적용 · '+('현재 프로필' if index is None else f'{index+1}번 프로필')+f' 설정 읽기·보존 확인 {number*100//len(FIELDS)}%')
        effects={}
        for trigger in range(2):
            for state in range(5):
                if index is None:
                    r=self.packet(0x12,bytes([trigger,state]),bytes([trigger,state]))
                    value=r[17:19]+r[6:17]
                else:
                    r=self.packet(0x15,bytes([index,trigger,state]),bytes([index,trigger,state]))
                    value=r[7:20]
                effects[f'{trigger}:{state}']=value.hex()
                if progress is not None:progress(len(FIELDS)+len(effects),total)
        return dict(fields=fields,effects=effects)
    def activate(self,index):
        self.packet(9,bytes([index]),bytes([index]))
        if self.c.studio.profile()['index']!=index:raise RuntimeError('프로필 전환 검증 실패')
    def check_profile(self,info):
        self.c.check();profile=self.c.studio.profile()
        name=bytes.fromhex(info['name']).decode('utf-8',errors='replace').rstrip('\0').strip()
        if (profile['index'],profile['name'])!=(info['index'],name):
            raise RuntimeError('쓰기 직전 프로필이 변경되었습니다. 추가 쓰기를 중단했습니다.')
        self.c.check()
    def save(self,info):
        self.check_profile(info)
        self.packet(8,bytes([info['index']])+bytes.fromhex(info['name']),bytes([info['index']]))
    def apply(self,original,rows,mask,disable_ps,folder,*,ps_enabled=None):
        if ps_enabled is True:mask|=ps_rows(rows)
        origin=original.profile.get('index')
        if original.firmware!='1.42.0' or origin is None or original.profile.get('edited',True):
            raise ValueError('공통 저장 전 현재 Studio 프로필의 미저장 변경을 먼저 저장하고 다시 조회하세요. 저장된 프로필이 필요합니다.')
        if self.c.read()!=original:raise RuntimeError('장치 설정이 바뀌었습니다. 다시 조회하세요.')
        slots=[];plans=[]
        ps_input=any(not mask&(1<<i) and int.from_bytes(r[:4],'little')&(1<<16) for i,r in enumerate(rows))
        for index in range(32):
            self.progress(f'공통 적용 준비 · 프로필 {index+1}/32 확인')
            info=self.info(index)
            if not info['valid']:continue
            if info['version']!=19:raise ValueError(f'{index+1}번은 구형 프로필입니다. Studio에서 확인·저장한 뒤 다시 시도하세요.')
            oldmask=int.from_bytes(self.field(index,0x6c)[:4],'little');oldps=self.field(index,0x0e)[0]
            targetps=resolve(oldps,disable_ps,ps_enabled)
            if ps_input and targetps:raise ValueError(f'{index+1}번 프로필에 PS 단축키가 켜져 있습니다. Studio PS 단축키 사용을 해제하세요.')
            slots.append(info)
            if oldmask!=mask or oldps!=targetps:
                self.progress(f'공통 적용 준비 · {index+1}번 프로필 백업 읽는 중')
                plans.append(dict(info=info,body=self.body(index)))
        if not any(s['index']==origin for s in slots):raise ValueError('현재 저장 프로필을 확인할 수 없습니다.')
        if self.c.read()!=original:raise RuntimeError('백업 중 설정이 변경되었습니다. 쓰지 않았습니다.')
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        path=folder/('common-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        journal=dict(firmware=original.firmware,origin=original.profile,original_rows=[r.hex() for r in original.rows],
                     original_mask=original.disabled,original_ps=original.ps_shortcut,slots=slots,plans=plans,completed=[],phase='backed_up')
        def record(phase):
            journal['phase']=phase
            temp=path.with_suffix('.tmp')
            with temp.open('w',encoding='utf8') as stream:
                json.dump(journal,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path)
        record('backed_up')
        try:
            record('applying_macro_table')
            result=self.c.apply(original,rows,mask,disable_ps,folder,ps_enabled=ps_enabled)
            for number,plan in enumerate(plans):
                info=plan['info'];index=info['index'];before=plan['body']
                self.progress(f'공통 저장 · {number+1}/{len(plans)} · {index+1}번 프로필 검증 중')
                if self.info(index)!=info or self.body(index)!=before:raise RuntimeError('백업 이후 저장 프로필이 변경되었습니다.')
                record(f'activating_{index}')
                self.activate(index)
                if self.body(None)!=before:raise RuntimeError('프로필 로드 시 다른 값이 정규화되었습니다. 해당 슬롯을 덮어쓰지 않았습니다.')
                oldmask=int.from_bytes(bytes.fromhex(before['fields'][str(0x6c)])[:4],'little')
                oldps=bytes.fromhex(before['fields'][str(0x0e)])[0];targetps=resolve(oldps,disable_ps,ps_enabled)
                write_policy(self.c,lambda:self.check_profile(info),oldmask,mask,oldps,targetps)
                expected=dict(fields=dict(before['fields']),effects=before['effects'])
                expected['fields'][str(0x6c)]=(mask.to_bytes(4,'little')+bytes(4)).hex()
                if oldps!=targetps:expected['fields'][str(0x0e)]=(bytes([targetps])+bytes(7)).hex()
                if self.body(None)!=expected:raise RuntimeError('저장 전 다른 설정 변화 감지 · 슬롯 저장 중단')
                if self.info(index)!=info or self.body(index)!=before:raise RuntimeError('저장 직전 원본 프로필 변경 감지 · 저장 중단')
                record(f'saving_{index}');self.save(info)
                if self.info(index)!=info or self.body(index)!=expected:raise RuntimeError('프로필 저장 후 검증 실패')
                journal['completed'].append(index);record(f'verified_{index}')
            if plans:
                record('restoring_selected_profile');self.activate(origin)
                result=self.c.read()
            if result.rows!=tuple(rows) or result.disabled!=mask or result.profile['index']!=origin or (ps_enabled is not None and result.ps_shortcut!=int(ps_enabled)):
                raise RuntimeError('최종 공통 설정 검증 실패')
            record('complete')
            return result,len(slots)
        except Exception as exc:
            raise RuntimeError(f'공통 적용 중단: {exc} · 일부 저장/현재 프로필 변경 가능. 완료 슬롯 {journal["completed"]}. 백업: {path}') from exc
