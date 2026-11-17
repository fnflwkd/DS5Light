"""Held-button turbo on virtual Xbox output only; no thread or device writes."""
# (label, state tuple index, button mask). Trigger entries gate their analog value.
TARGETS=(('A / ✕',0,0x1000),('B / ○',0,0x2000),('X / □',0,0x4000),('Y / △',0,0x8000),
         ('LB / L1',0,0x100),('RB / R1',0,0x200),('LT / L2',1,0),('RT / R2',2,0),
         ('L3',0,0x40),('R3',0,0x80),('↑',0,1),('↓',0,2),('←',0,4),('→',0,8),
         ('Back / Create',0,0x20),('Start / Options',0,0x10))
RATES=(5,10,15,20)

class Turbo:
    def __init__(self):
        self.settings=(frozenset(),10,frozenset(),0);self.reset()
    @property
    def config(self):return self.settings[:2]
    @property
    def toggles(self):return self.settings[2]
    def configure(self,targets,rate):self.configure_modes(targets,self.toggles,rate)
    def configure_modes(self,targets,toggles,rate):
        targets=frozenset(targets);toggles=frozenset(toggles)
        if type(rate) is not int or rate not in RATES or any(type(i) is not int or not 0<=i<25 for i in targets|toggles):raise ValueError('지원하지 않는 터보/토글 설정')
        if any(16<=i<24 and i not in toggles for i in targets):raise ValueError('스와이프 터보는 토글과 함께 사용하세요.')
        if (targets,rate,toggles)!=self.settings[:3]:self.settings=(targets,rate,toggles,self.settings[3]+1)
    def reset(self):
        self.previous=None;self.started={};self.latched={};self.down=set();self.pulses={}
    def levels(self,values,events,now,settings=None):
        config=self.settings if settings is None else settings;selected,rate,toggles=config[:3]
        held={i for i,v in enumerate(values) if v}
        if config!=self.previous:
            self.reset();self.previous=config;self.down=held & toggles
        # A held button at startup/config change must be released before latching.
        pressed=held|set(events)
        for i in pressed-self.down:
            if i in toggles:
                if i in self.latched:self.latched.pop(i)
                else:self.latched[i]=values[i] if i<16 else 255
            elif 16<=i<24:self.pulses[i]=now+.08
        self.down=pressed
        result=list(values)+[0]*16
        for i in toggles:result[i]=self.latched.get(i,0)
        for i,until in list(self.pulses.items()):
            if now>=until:self.pulses.pop(i)
            else:result[i]=255
        for i in selected:
            if not result[i]:self.started.pop(i,None);continue
            start=self.started.setdefault(i,now)
            if int(max(0,now-start)*rate*2)%2:result[i]=0
        return result
    def apply(self,state,now):
        if not self.config[0] and not self.toggles:return state
        values=[(255 if state[0]&mask else 0) if axis==0 else state[axis] for _,axis,mask in TARGETS]
        levels=self.levels(values,(),now);result=list(state)
        for i,(_,axis,mask) in enumerate(TARGETS):
            if axis==0:
                result[0]=(result[0]|mask) if levels[i] else (result[0]&~mask)
            else:result[axis]=levels[i]
        return tuple(result)

class SourceTurboPanel:
    """Controls the physical source chosen on the remap drawing."""
    def __init__(self,app,parent,remap):
        import tkinter as tk
        from tkinter import ttk
        from ui_help import help_icon
        self.app=app;self.remap=remap;self.last_view=None
        box=ttk.Frame(parent,padding=(8,4));box.pack(fill='x')
        self.enabled=tk.BooleanVar()
        self.toggle=ttk.Checkbutton(box,text='터보',variable=self.enabled,command=self.change);self.toggle.pack(side='left')
        help_icon(box,'버튼을 누르고 있는 동안 연타. 스와이프에서는 토글과 함께 사용합니다.')
        self.latched=tk.BooleanVar()
        self.latch_toggle=ttk.Checkbutton(box,text='토글',variable=self.latched,command=self.change_latch);self.latch_toggle.pack(side='left',padx=(8,0))
        help_icon(box,'한 번 누르거나 스와이프하면 입력 유지, 다시 하면 중지. 터보도 켜면 연타를 유지합니다.')
        self.rate=ttk.Combobox(box,values=[f'초당 {n}회' for n in RATES],state='disabled',width=11);self.rate.current(1);self.rate.pack(side='left',padx=8)
        self.rate.bind('<<ComboboxSelected>>',lambda e:self.change_rate())
        self.state_label=ttk.Label(box,text='',foreground='#d5ad70',width=22);self.state_label.pack(side='right',padx=4)
        self.clear_button=ttk.Button(box,text='터보·토글 모두 끄기',command=self.clear);self.clear_button.pack(side='left')
        ttk.Label(parent,text='터보·토글은 Xbox 360 호환 모드에서만 지원합니다.',style='Muted.TLabel').pack(anchor='w',padx=8)
        from ui_viewport import message_area
        self.note=ttk.Label(message_area(parent,2),text='',wraplength=680,style='Muted.TLabel');self.note.pack(anchor='w',padx=8)
        self.render()
    def source(self):
        from xbox_source_remap import INDEX
        from remapping import BUTTONS
        if self.remap.gesture:return None if self.remap.gesture&8 else 16+(self.remap.gesture&7)
        selected=[i for i,v in enumerate(self.remap.inputs) if v.get()]
        return (24 if BUTTONS[selected[0]]=='Touchpad' else INDEX.get(BUTTONS[selected[0]])) if len(selected)==1 else None
    def worker(self):return getattr(getattr(self.app,'xbox',None),'worker',None)
    def available(self):
        xbox=getattr(self.app,'xbox',None);w=self.worker()
        return bool(w and w.alive and w.updates>0 and getattr(w,'source_active',False) is True and not w.stop_event.is_set() and not w.paused.is_set() and not xbox.busy and not self.app.closing and not self.remap.busy and not getattr(self.app.studio_window,'busy',False))
    def reason(self):
        w=self.worker();xbox=getattr(self.app,'xbox',None)
        if not w or not w.alive:return 'Xbox OFF'
        if w.stop_event.is_set():return 'Xbox 종료 중'
        if self.remap.busy or getattr(self.app.studio_window,'busy',False):return '장치 설정 작업 중'
        if xbox.busy:return 'Xbox 관리 작업 중'
        if w.paused.is_set():return 'Xbox 입력 일시정지'
        if w.updates<=0:return '첫 입력 대기 중'
        if not getattr(w,'source_active',False):return getattr(w,'source_reason','') or '원본 버튼 처리 미준비 · 다시 조회하세요.'
        return ''
    def render(self,force=False):
        w=self.worker();source=self.source();active=self.available()
        config=w.turbo.config if w else (frozenset(),10)
        plan=getattr(w,'source_plan',None)
        active=active and plan is not None
        toggles=w.turbo.toggles if w else frozenset()
        holding=bool(w and w.turbo.latched.get(source,0))
        reason=self.reason()
        view=(active,source,config,toggles,holding,plan,reason)
        if not force and view==self.last_view:return
        self.last_view=view
        ready=active and source is not None and source not in plan.blocked and (source<16 or source in plan.swipes or source in plan.clicks)
        self.state_label.configure(text='' if ready else reason or ('키보드·마우스 리맵' if active and source in plan.blocked else '버튼 선택 필요'))
        self.toggle.configure(state='normal' if ready else 'disabled')
        self.latch_toggle.configure(state='normal' if ready else 'disabled')
        self.rate.configure(state='readonly' if ready else 'disabled')
        self.clear_button.configure(state='normal' if active else 'disabled')
        self.enabled.set(source in config[0]);self.latched.set(source in toggles);self.rate.current(RATES.index(config[1]))
        if ready:
            from xbox_source_remap import NAMES
            if source<16:
                target,keep=plan.mappings.get(source,(source,False));name=NAMES[source]
            elif source==24:
                target=plan.clicks[source];keep=False;name='터치패드 클릭'
            else:
                from remapping import SWIPE_DIRECTIONS
                target=plan.swipes[source];keep=False
                name=('오른쪽' if (source-16)&4 else '왼쪽')+' '+SWIPE_DIRECTIONS[(source-16)&3]+' 스와이프'
            text=name+' → '+' + '.join(TARGETS[i][0] for i in (target if isinstance(target,tuple) else (target,))) + (' · 원래 버튼도 함께' if keep else '')
            text+=' · '+('토글 연타' if source in toggles and source in config[0] else '토글 유지' if source in toggles else '누르는 동안 연타' if source in config[0] else '일반 입력')
            if source in toggles:text+=' · '+('입력 유지 중' if holding else '토글 대기')
        elif active and source in plan.blocked:text='키보드·마우스 출력은 Pico에서 유지합니다. 이 항목의 터보·토글은 지원하지 않습니다.'
        elif active:text='패드 버튼 또는 장치에 적용된 한 손가락 스와이프를 선택하세요.'
        else:text=reason or 'Xbox 360 호환 모드에서만 설정할 수 있습니다.'
        if w and not w.alive:text='Xbox 360 호환 모드를 켜면 터보를 설정할 수 있습니다.'
        self.note.configure(text=text)
        if not ready and w and w.alive:
            record=getattr(getattr(self.app,'xbox',None),'record',None)
            if callable(record):record('터보·토글 비활성: '+str(source)+' · '+text)
    def editable_source(self):
        w=self.worker();source=self.source();plan=getattr(w,'source_plan',None)
        if not self.available() or plan is None or source is None or source in plan.blocked or source>=16 and source not in plan.swipes and source not in plan.clicks:return None
        return w,source
    def change(self):
        selection=self.editable_source()
        if selection is None:self.render(True);return
        w,source=selection
        selected=set(w.turbo.config[0])
        if self.enabled.get():selected.add(source)
        else:selected.discard(source)
        toggles=set(w.turbo.toggles)
        if 16<=source<24 and source in selected:toggles.add(source)
        w.turbo.configure_modes(selected,toggles,w.turbo.config[1]);self.render(True)
    def change_latch(self):
        selection=self.editable_source()
        if selection is None:self.render(True);return
        w,source=selection;toggles=set(w.turbo.toggles);selected=set(w.turbo.config[0])
        if self.latched.get():toggles.add(source)
        else:
            toggles.discard(source)
            if 16<=source<24:selected.discard(source)
        w.turbo.configure_modes(selected,toggles,w.turbo.config[1]);self.render(True)
    def change_rate(self):
        selection=self.editable_source()
        if selection is None:self.render(True);return
        w,_=selection;index=self.rate.current()
        if 0<=index<len(RATES):w.turbo.configure(w.turbo.config[0],RATES[index])
        self.render(True)
    def clear(self):
        if not self.available():self.render(True);return
        w=self.worker();w.turbo.configure_modes([],[],w.turbo.config[1]);self.render(True)

