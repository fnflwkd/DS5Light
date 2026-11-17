"""Source-button remapping before merge; no device or OS I/O."""
from remapping import BUTTONS,OUTPUTS,EMPTY,editable,is_swipe,describe
from xbox_turbo import TARGETS
NAMES=('×','○','□','△','L1','R1','L2','R2','L3','R3','↑','↓','←','→','Create','Options')
INDEX={name:i for i,name in enumerate(NAMES)}
class Unsupported(ValueError):pass

def compile_plan(snapshot):
    mappings={};swipes={};clicks={};retained=0;blocked=set();seen_sources=set();seen_swipes=set();seen_touch=False
    def reject(message):
        raise Unsupported(f'{row+1}번 리맵 ({describe(record)[0]}): '+message)
    groups={}
    from pad_combo import tagged,valid_group
    for i,r in enumerate(snapshot.rows):
        if not snapshot.disabled&(1<<i) and tagged(r):groups[r[:6]]=[x for j,x in enumerate(snapshot.rows) if not snapshot.disabled&(1<<j) and x[:4]==r[:4] and x[4]==0]
    if any(not valid_group(g) for g in groups.values()):raise Unsupported("키 조합 항목이 일부 꺼졌거나 손상됐습니다. 조합을 다시 적용하세요.")
    passthrough={'Keyboard','Mouse left','Mouse right','Mouse middle','Wheel up','Wheel down'}
    for row,record in enumerate(snapshot.rows):
        if snapshot.disabled&(1<<row) or record==EMPTY:continue
        if is_swipe(record):
            if not editable(record):reject('고급 스와이프는 PC 처리에서 지원하지 않습니다.')
            key=16+(record[4]&15);target=OUTPUTS[record[17]]
            if key in seen_swipes:reject('같은 스와이프의 중복 리맵은 지원하지 않습니다.')
            seen_swipes.add(key)
            if target in passthrough:retained|=1<<row;blocked.add(key);continue
            if any(record[6:11]) or target not in INDEX:reject('특수 스와이프는 PC 처리에서 지원하지 않습니다.')
            swipes[key]=INDEX[OUTPUTS[record[17]]];continue
        chord=int.from_bytes(record[:4],'little')
        if not editable(record) or chord.bit_count()!=1:
            reject('조합·고급 매크로가 있어 터보·토글을 사용할 수 없습니다.')
        source=BUTTONS[chord.bit_length()-1];target=OUTPUTS[record[17]]
        if source=='Touchpad':
            if seen_touch and not tagged(record):reject('같은 터치패드 클릭의 중복 리맵은 지원하지 않습니다.')
            seen_touch=True
        if source=='Touchpad' and target in INDEX:
            if not record[5]&2 or any(record[6:11]):reject('고급 터치패드 출력은 PC 처리에서 지원하지 않습니다.')
            clicks[24]=tuple(INDEX[OUTPUTS[r[17]]] for r in groups[record[:6]]) if tagged(record) else INDEX[target];continue
        if source not in INDEX:
            if target in passthrough:
                retained|=1<<row
                if source=='Touchpad':blocked.add(24)
                continue  # Special-source keyboard/mouse stays entirely in Pico.
            reject('특수 버튼의 패드 출력은 PC 처리에서 지원하지 않습니다.')
        key=INDEX[source]
        if key in seen_sources:
            if tagged(record) and key in mappings:continue
            reject('같은 버튼의 중복 리맵은 지원하지 않습니다.')
        seen_sources.add(key)
        if target in passthrough:retained|=1<<row;blocked.add(key);continue
        if not record[5]&2 or any(record[6:11]):reject('고급 패드 출력은 PC 처리에서 지원하지 않습니다.')
        if target not in INDEX:
            reject('키보드·마우스·특수 버튼 리맵이 있어 버튼별 터보를 사용할 수 없습니다.')
        mappings[key]=(tuple(INDEX[OUTPUTS[r[17]]] for r in groups[record[:6]]) if tagged(record) else INDEX[target],not bool(record[5]&4))
    return Plan(mappings,swipes,retained,blocked,clicks)

class Plan:
    def __init__(self,mappings,swipes=None,retained=0,blocked=(),clicks=None):
        from xbox_swipe import Swipe
        self.clicks=dict(clicks or {});self.click_down=False
        self.retained=retained;self.blocked=frozenset(blocked)
        self.mappings=dict(mappings);self.swipes=dict(swipes or {});self.swipe=Swipe();self.last_modes=None;self.raw_modes=None;self.filtered_modes=None
    def reset(self):self.click_down=False;self.swipe.reset();self.last_modes=None;self.raw_modes=None;self.filtered_modes=None
    def process(self,state,turbo,now,trigger_down,raw=None):
        original_settings=turbo.settings
        if original_settings!=self.raw_modes:
            self.raw_modes=original_settings
            self.filtered_modes=(original_settings[0]-self.blocked,original_settings[1],original_settings[2]-self.blocked,original_settings[3]) if self.blocked else original_settings
        settings=self.filtered_modes
        if settings!=self.last_modes:self.swipe.reset();self.last_modes=settings
        prepared=list(state)
        for source,axis,down in ((INDEX['L2'],1,trigger_down[0]),(INDEX['R2'],2,trigger_down[1])):
            if source in self.mappings or source in settings[2]:prepared[axis]=max(1,state[axis]) if down else 0
        values=[(255 if prepared[0]&mask else 0) if axis==0 else prepared[axis] for _,axis,mask in TARGETS]
        if self.clicks:
            if raw is not None:self.click_down=bool(raw[10]&2)
            values.extend([0]*8+[255 if self.click_down else 0])
        events=tuple(i for i in self.swipe.update(raw,now) if i in self.swipes) if self.swipes else ()
        levels=turbo.levels(values,events,now,settings)
        for i,(_,axis,mask) in enumerate(TARGETS):
            if axis==0:prepared[0]=(prepared[0]|mask) if levels[i] else (prepared[0]&~mask)
            else:prepared[axis]=levels[i]
        effective_down=tuple(trigger_down[i] or INDEX[name] in settings[2] for i,name in enumerate(('L2','R2')))
        result=list(self.apply(tuple(prepared),effective_down,state))
        for source,target in (*self.swipes.items(),*self.clicks.items()):
            if not levels[source]:continue
            for destination in target if isinstance(target,tuple) else (target,):
                _,axis,mask=TARGETS[destination]
                if axis==0:result[0]|=mask
                else:result[axis]=max(result[axis],levels[source])
        return tuple(result)
    def apply(self,state,trigger_down=None,original=None):
        if not self.mappings:return state
        # Merge contributions only AFTER each physical source was turbo-gated.
        known=sum(mask for _,axis,mask in TARGETS if axis==0)
        result=[state[0]&~known,0,0,*state[3:]]
        for source,(_,axis,mask) in enumerate(TARGETS):
            value=(255 if state[0]&mask else 0) if axis==0 else state[axis]
            target,keep=self.mappings.get(source,(source,False))
            if axis and source in self.mappings and trigger_down is not None and not trigger_down[axis-1]:
                target,keep=source,False;value=original[axis]
            if not value:continue
            destinations=target if isinstance(target,tuple) else (target,)
            for index in ((source,)+destinations if keep else destinations):
                _,out_axis,out_mask=TARGETS[index]
                if out_axis==0:result[0]|=out_mask
                else:result[out_axis]=max(result[out_axis],value)
        return tuple(result)
