import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import json
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
from dataclasses import asdict
from audio import Engine, InstanceLock, devices
from core import Controls
from battery import BatteryMonitor,battery_text,BatteryIcon
from process_list import process_list
from session_settings import SessionStore
from presets import PresetStore, SLOT_COUNT, match_game
from localization import tr, LANGUAGE, save_language, canonical_device, display_device

BG='#151b25'; CARD='#202937'; FG='#e5edf7'; MUTED='#9cacc1'; BORDER='#344256'; ACCENT='#82e5cc'; DISABLED='#647184'
AUTO=tr('자동 선택 · 기존 BAT 방식')
CHANNELS={tr('5.1채널 (홈시어터)'):6,tr('2채널 (스테레오)'):2}
PROCESS_SORT={('이름순 A–Z' if LANGUAGE=='ko' else 'Name A–Z'):'name',('CPU 사용률순' if LANGUAGE=='ko' else 'CPU usage'):'cpu'}
LIMITERS={tr('초과분 자르기'):'hard',tr('부드러운 제한'):'soft'}

class Switch(tk.Canvas):
    """Static native Tk switch: no animation, web engine or polling."""
    def __init__(self,parent,variable,command):
        super().__init__(parent,width=44,height=26,bg=CARD,highlightthickness=1,
                         highlightbackground=CARD,highlightcolor=ACCENT,takefocus=1,cursor='hand2')
        self.variable=variable; self.command=command; self.enabled=True
        self.bind('<Button-1>',lambda e:self.invoke())
        self.bind('<space>',lambda e:self.invoke())
        self.bind('<Return>',lambda e:self.invoke())
        variable.trace_add('write',lambda *args:self.draw())
        self.draw()
    def invoke(self):
        if self.enabled:
            self.variable.set(not self.variable.get()); self.command()
        return 'break'
    def set_enabled(self,enabled):
        if self.enabled==enabled: return
        self.enabled=enabled; self.configure(takefocus=int(enabled),cursor='hand2' if enabled else 'arrow'); self.draw()
    def draw(self):
        self.delete('all')
        on=self.variable.get(); color=ACCENT if on and self.enabled else '#435166'
        self.create_oval(2,3,22,23,fill=color,outline=color)
        self.create_oval(22,3,42,23,fill=color,outline=color)
        self.create_rectangle(12,3,32,23,fill=color,outline=color)
        x=25 if on else 5
        knob='#173d34' if on and self.enabled else '#b3c0d0' if self.enabled else '#788597'
        self.create_oval(x,6,x+14,20,fill=knob,outline=knob)

class App:
    def __init__(self,root):
        self.session_timer=None;self.session_ready=False;self.games_busy=False;self.games_queue=queue.Queue()
        self.root=root; self.engine=None; self.connection=None; self.last_render=None; self.device_channel_cache={}
        root.title('DS5 Light · 0.9.8'); root.configure(bg=BG)
        root.iconbitmap(default=str(Path(__file__).resolve().parent/'assets'/'dslight.ico'))
        root.geometry('1120x980'); root.minsize(1060,980)
        style=ttk.Style(root); style.theme_use('clam')
        style.configure('.',font=('맑은 고딕',10),background=CARD,foreground=FG)
        style.configure('TFrame',background=CARD)
        style.configure('TLabel',background=CARD,foreground=FG)
        style.configure('Muted.TLabel',foreground=MUTED,font=('맑은 고딕',9))
        style.configure('TButton',padding=(10,5),background='#293546',foreground=FG,bordercolor=BORDER,relief='flat')
        style.map('TButton',background=[('active','#35485d'),('disabled','#242e3b')],foreground=[('disabled',DISABLED)])
        style.configure('Accent.TButton',background=ACCENT,foreground='#173d34',font=('맑은 고딕',10,'bold'))
        style.map('Accent.TButton',background=[('active','#a3efdb'),('disabled','#334b49')],foreground=[('disabled',DISABLED)])
        style.configure('Selected.TButton',background='#2a5047',foreground='#b4f4e1',bordercolor=ACCENT)
        style.configure('TCombobox',fieldbackground='#18212e',background='#293546',arrowcolor=MUTED,bordercolor=BORDER,padding=4)
        style.map('TCombobox',fieldbackground=[('readonly','#18212e'),('disabled','#27303c')],foreground=[('disabled',DISABLED),('readonly',FG)])
        style.configure('TEntry',fieldbackground='#18212e',bordercolor=BORDER,padding=6)
        style.configure('TCheckbutton',background=CARD,foreground=FG)
        style.map('TCheckbutton',foreground=[('disabled',DISABLED)],background=[('active',CARD)])
        style.configure('TRadiobutton',background=CARD,foreground=FG)
        style.map('TRadiobutton',foreground=[('disabled',DISABLED)],background=[('active',CARD)])
        style.configure('Horizontal.TScale',background=CARD,troughcolor='#131c28')
        root.option_add('*TCombobox*Listbox.background','#18212e'); root.option_add('*TCombobox*Listbox.foreground',FG)
        root.option_add('*TCombobox*Listbox.selectBackground','#2d594e')
        config_path=Path(sys.executable).parent/'default_config.json' if getattr(sys,'frozen',False) else Path(__file__).with_name('default_config.json')
        self.controls=Controls(**json.loads(config_path.read_text(encoding='utf-8'))) if config_path.exists() else Controls()
        if self.controls.mode not in ('normal','pure') or not 0<=self.controls.strength<=1 or self.controls.limiter not in ('soft','hard'):
            raise ValueError(tr('PC 기본 설정 오류'))
        preset_path=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'DS5Light'/'presets.json'
        if '--preset-test-path' in sys.argv: preset_path=Path(sys.argv[sys.argv.index('--preset-test-path')+1])
        session_path=preset_path.with_name('last_settings.json')
        if '--preset-test-path' in sys.argv:session_path=preset_path.with_suffix('.session.json')
        self.session=SessionStore(session_path)
        self.process_order=tk.StringVar(value=list(PROCESS_SORT)[0])
        self.game_selection=tk.StringVar()
        self.store=PresetStore(preset_path); self.desired_game=''; self.game_map={}; self.game_names={}
        self.ds=devices(); self.inputs=[AUTO]+[d['name'] for d in self.ds if d.get('isLoopbackDevice') and 'dualsense' not in d['name'].lower()]
        self.outputs=[AUTO]+[d['name'] for d in self.ds if d['maxOutputChannels']>=4 and 'dualsense' in d['name'].lower()]
        c=self.controls
        self.scope=tk.StringVar(value='device'); self.channel=tk.StringVar(value=list(CHANNELS)[0])
        self.source=tk.StringVar(value=AUTO); self.destination=tk.StringVar(value=AUTO)
        self.mode=tk.StringVar(value=c.mode); self.filter_on=tk.BooleanVar(value=not c.bypass)
        self.strength=tk.DoubleVar(value=c.strength*100); self.bg=tk.BooleanVar(value=c.background); self.transient=tk.BooleanVar(value=c.transient)
        self.center=tk.BooleanVar(value=c.center); self.rear=tk.BooleanVar(value=c.rear); self.lfe=tk.BooleanVar(value=c.lfe)
        self.limiter=tk.StringVar(value=next(k for k,v in LIMITERS.items() if v==c.limiter))
        self.slot_name=tk.StringVar(value=tr('게임 설정')); self.notice=tk.StringVar(value=tr('슬롯 선택 후 불러오기 · 저장은 선택한 슬롯을 교체합니다.'))
        self.status=tk.StringVar(value=tr('정지 · 기존 BAT를 종료한 후 시작하세요'))
        # Layout: header, source/profile card, two peer cards, connection, footer.
        outer=tk.Frame(root,bg=BG); outer.pack(fill='both',expand=True,padx=24,pady=12); outer.columnconfigure(0,weight=1); outer.rowconfigure(2,weight=1)
        head=tk.Frame(outer,bg=BG); head.grid(row=0,column=0,sticky='ew',pady=(0,12))
        tk.Label(head,text='DS5 LIGHT',bg=BG,fg=ACCENT,font=('Segoe UI',10,'bold')).pack(anchor='w')
        tk.Label(head,text=tr('오디오햅틱'),bg=BG,fg=FG,font=('맑은 고딕',21,'bold')).pack(side='left',pady=(6,0))
        tk.Label(head,text=tr('게임 소리는 그대로, 동글로 보내는 복사본만 처리'),bg=BG,fg=MUTED,font=('맑은 고딕',10)).pack(side='left',padx=20,pady=(10,0))
        self.language_choice=ttk.Combobox(head,values=['한국어','English'],state='readonly',width=10)
        self.language_choice.set('한국어' if LANGUAGE=='ko' else 'English'); self.language_choice.pack(side='right',padx=(12,0))
        self.language_choice.bind('<<ComboboxSelected>>',self.change_language)
        tk.Label(head,text='Language',bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(side='right')
        self.badge=tk.Label(head,text=tr('정지'),bg='#293646',fg=MUTED,padx=12,pady=5); self.badge.pack(side='right')
        top=self.card(outer); top.grid(row=1,column=0,sticky='ew',pady=(0,12)); top.columnconfigure(0,weight=1,uniform='top'); top.columnconfigure(1,weight=1,uniform='top')
        source_area=ttk.Frame(top); source_area.grid(row=0,column=0,sticky='nsew',padx=(0,16))
        preset_area=ttk.Frame(top); preset_area.grid(row=0,column=1,sticky='nsew')
        ttk.Label(source_area,text=tr('소리 받을 곳'),style='Muted.TLabel').pack(anchor='w')
        radios=ttk.Frame(source_area); radios.pack(fill='x',pady=(4,6)); self.scope_buttons=[]
        for text,value in [(tr('장치 전체'),'device'),(tr('선택한 게임만'),'process')]:
            b=ttk.Radiobutton(radios,text=text,value=value,variable=self.scope,command=self.render); b.pack(side='left',padx=(0,8)); self.scope_buttons.append(b)
        gr=ttk.Frame(source_area); gr.pack(fill='x')
        self.game=ttk.Combobox(gr,state='disabled',width=23,textvariable=self.game_selection); self.game.pack(side='left',fill='x',expand=True)
        self.game.bind('<<ComboboxSelected>>',self.game_selected)
        self.refresh_button=ttk.Button(gr,text=tr('새로고침'),command=self.refresh_games); self.refresh_button.pack(side='left',padx=(6,0))
        order_row=ttk.Frame(radios);order_row.pack(side='right')
        ttk.Label(order_row,text='정렬' if LANGUAGE=='ko' else 'Sort',style='Muted.TLabel').pack(side='left',padx=(0,8))
        self.order_box=ttk.Combobox(order_row,values=list(PROCESS_SORT),textvariable=self.process_order,state='readonly',width=13);self.order_box.pack(side='left')
        self.order_box.bind('<<ComboboxSelected>>',lambda e:self.refresh_games())
        ttk.Label(preset_area,text=tr('게임별 프리셋'),style='Muted.TLabel').pack(anchor='w')
        pr=ttk.Frame(preset_area); pr.pack(fill='x',pady=(6,0))
        self.slot=ttk.Combobox(pr,state='readonly',width=21); self.slot.pack(side='left',fill='x',expand=True)
        self.slot.bind('<<ComboboxSelected>>',self.slot_selected)
        self.load_button=ttk.Button(pr,text=tr('불러오기'),command=self.load_slot); self.load_button.pack(side='left',padx=5)
        ttk.Button(pr,text=tr('저장'),command=self.save_prompt).pack(side='left')
        ttk.Label(preset_area,textvariable=self.notice,style='Muted.TLabel',wraplength=405,font=('맑은 고딕',9)).pack(anchor='w',pady=(10,0))
        cards=tk.Frame(outer,bg=BG); cards.grid(row=2,column=0,sticky='nsew'); cards.columnconfigure(0,weight=1,uniform='cards'); cards.columnconfigure(1,weight=1,uniform='cards'); cards.rowconfigure(0,weight=0); cards.rowconfigure(1,weight=1)
        left=self.card(cards); left.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        right=self.card(cards); right.grid(row=1,column=0,sticky='nsew',padx=(0,8),pady=(10,0))
        studio_card=self.card(cards);studio_card.grid(row=0,column=1,rowspan=2,sticky='nsew',padx=(8,0))
        from studio_ui import StudioWindow
        self.studio_window=StudioWindow(self,parent=studio_card,auto_read='--preset-test-path' not in sys.argv and '--smoke-test' not in sys.argv)
        ttk.Label(left,text=tr('01   사용할 채널'),font=('맑은 고딕',12,'bold')).pack(anchor='w')
        self.channel_choice=ttk.Combobox(left,values=list(CHANNELS),textvariable=self.channel,state='readonly')
        self.channel_choice.pack(fill='x',pady=(10,0))
        self.channel_choice.bind('<<ComboboxSelected>>',lambda e:self.render())
        self.channel_note=ttk.Label(left,style='Muted.TLabel',wraplength=390); # Capture format is also shown in the connection summary.
        self.front_label=ttk.Label(left,text=tr('전면 L / R     항상 사용 · 기본 100%')); self.front_label.pack(anchor='w',pady=3)
        self.channel_labels=[]; self.mix_switches=[]
        for label,var in [(tr('후방 L / R'),self.rear),(tr('센터 · 대사도 포함'),self.center),(tr('LFE 저음'),self.lfe)]:
            tk.Frame(left,bg=BORDER,height=1).pack(fill='x',pady=2)
            row=ttk.Frame(left); row.pack(fill='x',pady=1)
            lab=ttk.Label(row,text=label); lab.pack(side='left'); self.channel_labels.append(lab)
            sw=Switch(row,var,self.update_controls); sw.pack(side='right'); self.mix_switches.append(sw)
        self.limit_label=ttk.Label(left,text=tr('채널 합산 시 큰 소리가 겹칠 때'),style='Muted.TLabel'); self.limit_label.pack(anchor='w',pady=(8,4))
        self.limiter_box=ttk.Combobox(left,values=list(LIMITERS),textvariable=self.limiter,state='readonly'); self.limiter_box.pack(fill='x')
        self.limiter_box.bind('<<ComboboxSelected>>',lambda e:self.update_controls())
        self.mix_note=ttk.Label(left,style='Muted.TLabel',wraplength=390,font=('맑은 고딕',9)); self.mix_note.pack(anchor='w',pady=(10,0))
        fh=ttk.Frame(right); fh.pack(fill='x')
        ttk.Label(fh,text=tr('02   PC 억제 필터'),font=('맑은 고딕',12,'bold')).pack(side='left')
        self.filter_switch=Switch(fh,self.filter_on,self.update_controls); self.filter_switch.pack(side='right')
        self.filter_badge=ttk.Label(fh); self.filter_badge.pack(side='right',padx=7)
        # Keep the integrated filter compact; detailed help remains available.
        self.filter_widgets=[]; self.style_buttons=[]
        sr=ttk.Frame(right); sr.pack(fill='x')
        for i,(label,v) in enumerate([(tr('디테일'),30),(tr('균형'),55),(tr('억제'),80)]):
            sr.columnconfigure(i,weight=1)
            b=ttk.Button(sr,text=label,command=lambda value=v:self.set_strength(value)); b.grid(row=0,column=i,sticky='ew',padx=(0,5) if i<2 else 0)
            self.filter_widgets.append(b); self.style_buttons.append((b,v))
        vr=ttk.Frame(right); vr.pack(fill='x',pady=(10,3)); ttk.Label(vr,text=tr('억제 강도'),style='Muted.TLabel').pack(side='left')
        self.value_label=ttk.Label(vr); self.value_label.pack(side='right')
        self.scale=ttk.Scale(right,from_=0,to=100,variable=self.strength,command=lambda v:self.update_controls()); self.scale.pack(fill='x'); self.filter_widgets.append(self.scale)
        ends=ttk.Frame(right); ends.pack(fill='x',pady=(3,5)); ttk.Label(ends,text=tr('효과 보존 우선'),style='Muted.TLabel').pack(side='left'); ttk.Label(ends,text=tr('억제 우선'),style='Muted.TLabel').pack(side='right')
        self.details_button=ttk.Button(right,text=tr('세부 필터 설정 ▸'),command=self.toggle_details); self.details_button.pack(anchor='w')
        self.advanced=ttk.Frame(right); self.advanced_open=False
        for text,var in [(tr('배경 대역 억제'),self.bg),(tr('변화량 보호'),self.transient)]:
            b=ttk.Checkbutton(self.advanced,text=text,variable=var,command=self.update_controls); b.pack(side='left',padx=(0,12)); self.filter_widgets.append(b)
        self.filter_note=ttk.Label(right,style='Muted.TLabel',wraplength=390,font=('맑은 고딕',9)); self.filter_note.pack(anchor='w',pady=(12,0))
        connect=tk.Frame(outer,bg=BG); connect.grid(row=3,column=0,sticky='ew',pady=(10,10))
        # Studio controls are embedded in the main window.
        ttk.Button(connect,text=tr('연결 설정 · 도움말'),command=self.open_connection).pack(side='left')
        self.connection_summary=tk.Label(connect,bg=BG,fg=MUTED,font=('맑은 고딕',9)); self.connection_summary.pack(side='left',padx=13)
        footer=self.card(outer); footer.grid(row=4,column=0,sticky='ew')
        buttons=ttk.Frame(footer); buttons.pack(side='right')
        self.stop_button=ttk.Button(buttons,text=tr('정지'),command=self.stop,state='disabled'); self.stop_button.pack(side='left',padx=(0,8))
        self.start_button=ttk.Button(buttons,text=tr('▶  시작'),command=self.start,style='Accent.TButton',width=11); self.start_button.pack(side='left')
        self.flow=ttk.Label(footer,foreground=ACCENT); self.flow.pack(anchor='w')
        self.status_label=ttk.Label(footer,textvariable=self.status,style='Muted.TLabel',wraplength=620,font=('맑은 고딕',9)); self.status_label.pack(anchor='w',pady=(5,0))
        self.battery=BatteryMonitor()
        battery_row=ttk.Frame(footer);battery_row.pack(anchor='w',fill='x',pady=(5,0))
        self.battery_icon=BatteryIcon(battery_row,self.battery.refresh,bg=CARD,fg=MUTED,fill=ACCENT);self.battery_icon.pack(side='left',padx=(0,8))
        self.battery_label=ttk.Label(battery_row,text=battery_text(self.battery,LANGUAGE),style='Muted.TLabel',font=('맑은 고딕',9),cursor='hand2')
        self.battery_label.pack(side='left')
        self.battery_label.bind('<Button-1>',lambda e:self.battery.refresh())
        self.refresh_slots(); self.restore_session(); self.render()
        self.session_ready=True
        for var in (self.scope,self.channel,self.source,self.destination,self.mode,self.filter_on,self.strength,self.bg,self.transient,self.center,self.rear,self.lfe,self.limiter,self.process_order):
            var.trace_add('write',self.schedule_session)
        if self.session.error:self.status.set(('마지막 설정 파일 오류 · 원본 보존: ' if LANGUAGE=='ko' else 'Last settings unreadable; preserved: ')+self.session.error)
        if self.store.error: root.after(100,lambda:messagebox.showerror(tr('프리셋 파일 오류'),str(self.store.path)+'\n'+tr(self.store.error)+tr('\n기존 파일을 보존하기 위해 저장이 차단됩니다.'),parent=root))
        root.after(150,self.refresh_games); root.after(1000,self.tick)
    def game_selected(self,event=None):
        self.desired_game=self.game_names.get(self.game.get(),'');self.schedule_session()
    def schedule_session(self,*args):
        if not self.session_ready or '--smoke-test' in sys.argv:return
        if self.session_timer:self.root.after_cancel(self.session_timer)
        self.session_timer=self.root.after(800,self.save_session)
    def save_session(self):
        if self.session_timer:self.root.after_cancel(self.session_timer);self.session_timer=None
        if not self.session_ready or '--smoke-test' in sys.argv:return
        try:
            c=dict(mode=self.mode.get(),bypass=not self.filter_on.get(),strength=self.strength.get()/100,
                   background=self.bg.get(),transient=self.transient.get(),rear=self.rear.get(),lfe=self.lfe.get(),center=self.center.get(),limiter=LIMITERS[self.limiter.get()])
            settings=dict(name='Last settings',game_exe=self.game_names.get(self.game.get(),self.desired_game),scope=self.scope.get(),channels=CHANNELS[self.channel.get()],input=canonical_device(self.source.get()),output=canonical_device(self.destination.get()),controls=c)
            self.session.save(dict(version=1,settings=settings,sort=PROCESS_SORT[self.process_order.get()],slot=max(0,self.slot.current()),details=self.advanced_open))
        except Exception as exc:self.status.set(('마지막 설정 저장 실패: ' if LANGUAGE=='ko' else 'Could not save last settings: ')+str(exc))
    def restore_session(self):
        if '--smoke-test' in sys.argv or not self.session.value:return
        doc=self.session.value;item=doc['settings'];c=Controls(**item['controls'])
        self.desired_game=item['game_exe'];self.scope.set(item['scope'])
        self.channel.set(next(k for k,v in CHANNELS.items() if v==item['channels']))
        self.source.set(display_device(item['input']));self.destination.set(display_device(item['output']))
        self.mode.set(c.mode);self.filter_on.set(not c.bypass);self.strength.set(c.strength*100)
        self.bg.set(c.background);self.transient.set(c.transient);self.center.set(c.center);self.rear.set(c.rear);self.lfe.set(c.lfe)
        self.limiter.set(next(k for k,v in LIMITERS.items() if v==c.limiter));self.controls=c
        self.process_order.set(next(k for k,v in PROCESS_SORT.items() if v==doc['sort']))
        self.slot.current(doc['slot']);self.slot_selected()
        if doc['details']:self.toggle_details()
        self.status.set('마지막 설정 복원 · 시작을 눌러 실행하세요.' if LANGUAGE=='ko' else 'Last settings restored. Press Start to run.')
    def open_studio(self):
        from studio_ui import StudioWindow
        previous=getattr(self,'studio_window',None)
        if previous is not None and previous.win.winfo_exists():
            previous.win.focus_set(); return
        self.studio_window=StudioWindow(self)
    def change_language(self,event=None):
        code='ko' if self.language_choice.get()=='한국어' else 'en'
        try:
            save_language(code)
            self.notice.set('다음 실행부터 한국어로 표시됩니다.' if code=='ko' else 'English will be used next time you open the app.')
        except Exception as exc:
            messagebox.showerror(tr('저장 실패'),tr(str(exc)),parent=self.root)
    def card(self,parent):
        return tk.Frame(parent,bg=CARD,highlightbackground=BORDER,highlightthickness=1,padx=14,pady=10)
    def capture_channels(self):
        if self.engine: return self.engine.capture_channels
        if self.scope.get()=='process': return CHANNELS[self.channel.get()]
        matches=[d for d in self.ds if d['name']==self.source.get() and d.get('isLoopbackDevice')]
        return int(matches[0]['maxInputChannels']) if len(matches)==1 else self.device_channel_cache.get(self.source.get())
    def update_controls(self):
        self.controls=Controls(mode=self.mode.get(),bypass=not self.filter_on.get(),strength=self.strength.get()/100,
            background=self.bg.get(),transient=self.transient.get(),rear=self.rear.get(),lfe=self.lfe.get(),center=self.center.get(),limiter=LIMITERS[self.limiter.get()])
        if self.engine: self.engine.controls=self.controls
        self.render()
    def render(self):
        ch=self.capture_channels(); active=bool(self.engine); filtering=self.filter_on.get()
        if self.scope.get()=='device' and ch in (2,6):
            self.device_channel_cache[self.source.get()]=ch
            self.channel.set(next(k for k,v in CHANNELS.items() if v==ch))
        state=(ch,active,filtering,self.scope.get(),self.channel.get(),self.source.get(),self.destination.get(),self.mode.get(),round(self.strength.get(),3),self.rear.get(),self.lfe.get(),self.center.get(),self.limiter.get())
        if state==self.last_render: return
        self.last_render=state
        available=ch==6 or ch is None and CHANNELS[self.channel.get()]==6
        for sw in self.mix_switches: sw.set_enabled(available)
        for lab in self.channel_labels+[self.limit_label]: lab.configure(foreground=FG if available else DISABLED)
        self.limiter_box.configure(state='readonly' if available else 'disabled')
        note=(tr('6ch 입력 · 센터 포함') if self.center.get() else tr('6ch 입력 · 센터 제외')) if available else tr('2ch 입력 · 좌우 스테레오') if ch==2 else tr(f'{ch}ch 입력 · 채널 추가 미지원') if ch else tr('입력 채널 · 시작 후 확인')
        self.channel_note.configure(text=(self.channel.get()+tr(' 준비 · 실제 형식은 시작 후 확인') if ch is None else tr('2채널 선택 · 전면 L/R만 사용') if CHANNELS[self.channel.get()]==2 else tr('5.1채널 선택 · 후방/센터/LFE 추가 가능') if available else tr('5.1채널 선택 · 6ch 입력 연결 대기'))+'')
        choices=[next(k for k,v in CHANNELS.items() if v==ch)] if self.scope.get()=='device' and ch in (2,6) else list(CHANNELS)
        self.channel_choice.configure(values=choices,state='disabled' if active or self.scope.get()=='device' and ch not in (2,6) else 'readonly')
        self.front_label.configure(text=tr('전면 L / R     항상 사용 · 기본 100%') if available else tr('입력 L / R     항상 사용'))
        self.mix_note.configure(text=tr('대사에 진동이 생기면 센터를 꺼 보세요.\nBGM 저음의 진동이 거슬리면 LFE를 꺼 보세요.') if available else tr('2채널은 추가 채널 합산이 없어 합산 제한을 사용하지 않습니다.\n5.1채널로 돌아오면 저장된 선택을 다시 사용합니다.') if ch==2 else tr('실제 입력이 표준 6ch일 때만 사용할 수 있습니다.\n자동 장치는 시작 후 Windows 캡처 형식을 확인합니다.'))
        self.filter_badge.configure(text=tr('켜짐') if filtering else tr('꺼짐'),foreground=ACCENT if filtering else MUTED)
        for w in self.filter_widgets: w.configure(state='normal' if filtering else 'disabled')
        for b,v in self.style_buttons: b.configure(style='Selected.TButton' if abs(self.strength.get()-v)<.1 and filtering else 'TButton')
        self.value_label.configure(text=f'{self.strength.get():.0f}%',foreground=FG if filtering else DISABLED)
        self.filter_note.configure(text=tr('끄면 PC 억제만 생략합니다.\n채널 선택과 Studio 처리는 유지됩니다.') if filtering else tr('PC 억제를 생략 중입니다.\n채널 선택·합산 제한·Studio 처리는 그대로입니다.'))
        for b in self.scope_buttons: b.configure(state='disabled' if active else 'normal')
        self.game.configure(state='readonly' if self.scope.get()=='process' and not active and not self.games_busy else 'disabled')
        self.refresh_button.configure(state='normal' if self.scope.get()=='process' and not active and not self.games_busy else 'disabled')
        self.order_box.configure(state='disabled' if active or self.games_busy else 'readonly')
        self.load_button.configure(state='disabled' if active else 'normal')
        self.start_button.configure(state='disabled' if active or self.games_busy else 'normal'); self.stop_button.configure(state='normal' if active else 'disabled')
        route=tr('선택 게임') if self.scope.get()=='process' else tr('장치 전체')
        self.flow.configure(text=tr(f'{route} → 채널 선택 → PC 필터 ')+(tr('켜짐') if filtering else tr('꺼짐'))+' → Studio' if self.mode.get()=='normal' else tr('퓨어 미지원 · 추가 오디오 출력 무음'))
        self.connection_summary.configure(text=tr(f"{'일반 모드' if self.mode.get()=='normal' else '퓨어 · 무음'}   ·   {self.channel.get()} · 캡처 {self.engine.capture_channels if self.engine and self.engine.capture_channels else '대기'}ch   ·   출력: ")+(tr('자동 선택') if self.destination.get()==AUTO else self.destination.get()[:28]))
        self.badge.configure(text=tr('실행 중') if active else tr('정지'),fg=ACCENT if active else MUTED)
        if self.connection and self.connection.winfo_exists(): self.render_connection()
    def set_strength(self,value): self.strength.set(value); self.update_controls()
    def toggle_details(self):
        self.schedule_session()
        self.advanced_open=not self.advanced_open
        if self.advanced_open: self.advanced.pack(fill='x',after=self.details_button,pady=(10,0))
        else: self.advanced.pack_forget()
        self.details_button.configure(text=tr('세부 필터 설정 ▾') if self.advanced_open else tr('세부 필터 설정 ▸'))
    def refresh_games(self):
        if self.games_busy or self.engine:return
        self.games_busy=True;self.refresh_button.configure(state='disabled');self.order_box.configure(state='disabled')
        self.game.configure(state='disabled');self.start_button.configure(state='disabled')
        order=PROCESS_SORT[self.process_order.get()]
        def work():
            try:self.games_queue.put((process_list(order),None))
            except Exception as exc:self.games_queue.put((None,str(exc)))
        threading.Thread(target=work,daemon=True).start();self.root.after(100,self.finish_games)
    def finish_games(self):
        try:rows,error=self.games_queue.get_nowait()
        except queue.Empty:self.root.after(100,self.finish_games);return
        self.games_busy=False
        if error:
            self.game_map.clear();self.game_names.clear();self.game.set('');self.game.configure(values=[])
            self.status.set(tr('게임 목록 조회 실패: ')+error)
        else:
            selected=self.game_map.get(self.game.get());selected_name=self.game_names.get(self.game.get());self.game_map.clear();self.game_names.clear()
            for name,pid,cpu in rows:
                suffix='' if PROCESS_SORT[self.process_order.get()]=='name' else (' · CPU —' if cpu is None else f' · CPU {cpu:.1f}%')
                key=f'{name} · PID {pid}'+suffix;self.game_map[key]=pid;self.game_names[key]=name
            self.game.configure(values=list(self.game_map));self.game.set('')
            if any(v==selected and self.game_names[k]==selected_name for k,v in self.game_map.items()):self.game.set(next(k for k,v in self.game_map.items() if v==selected and self.game_names[k]==selected_name))
            elif self.desired_game:
                pid=match_game(self.desired_game,[(self.game_names[k],v) for k,v in self.game_map.items()])
                self.game.set(next((k for k,v in self.game_map.items() if v==pid),''))
                if pid is None:self.status.set(self.desired_game+tr(' · 미실행 또는 같은 이름이 여러 개입니다. 실행 후 새로고침/직접 선택하세요.'))
        self.last_render=None;self.render()
    def refresh_slots(self,index=0):
        self.slot.configure(values=[f'{i+1:02d} · '+(item['name'] if item else tr('빈 슬롯')) for i,item in enumerate(self.store.slots)]); self.slot.current(index)
    def slot_selected(self,event=None):
        item=self.store.slots[self.slot.current()]; self.slot_name.set(item['name'] if item else tr('게임 설정'));self.schedule_session()
    def save_prompt(self):
        name=simpledialog.askstring(tr('프리셋 저장'),tr(f'{self.slot.current()+1:02d}번 슬롯 이름\n저장하면 해당 슬롯의 설정을 교체합니다.'),initialvalue=self.slot_name.get(),parent=self.root)
        if name is not None: self.slot_name.set(name.strip()); self.save_slot()
    def save_slot(self):
        try:
            self.update_controls(); i=self.slot.current()
            self.store.save(i,dict(name=self.slot_name.get(),game_exe=self.game_names.get(self.game.get(),self.desired_game),
                scope=self.scope.get(),channels=CHANNELS[self.channel.get()],input=canonical_device(self.source.get()),output=canonical_device(self.destination.get()),controls=asdict(self.controls)))
            self.refresh_slots(i); self.notice.set(tr(f'{i+1:02d}번 저장됨 · ')+self.slot_name.get())
        except Exception as exc: messagebox.showerror(tr('프리셋 저장 실패'),tr(str(exc)),parent=self.root)
    def load_slot(self):
        if self.engine: return
        item=self.store.slots[self.slot.current()]
        if item is None: self.notice.set(tr('빈 슬롯입니다. 설정을 맞춘 뒤 저장을 누르세요.')); return
        self.desired_game=item['game_exe']; self.game.set(''); self.scope.set(item['scope'])
        self.channel.set(next(k for k,v in CHANNELS.items() if v==item['channels']))
        self.source.set(display_device(item['input'])); self.destination.set(display_device(item['output'])); c=Controls(**item['controls'])
        self.mode.set(c.mode); self.filter_on.set(not c.bypass); self.strength.set(c.strength*100)
        self.bg.set(c.background); self.transient.set(c.transient); self.rear.set(c.rear); self.lfe.set(c.lfe); self.center.set(c.center)
        self.limiter.set(next(k for k,v in LIMITERS.items() if v==c.limiter)); self.slot_name.set(item['name'])
        self.update_controls(); self.refresh_games(); self.notice.set(tr('불러옴 · ')+item['name']+tr(' · 시작을 눌러 적용'))
        if (self.scope.get()=='device' and self.source.get() not in self.inputs) or self.destination.get() not in self.outputs:
            self.status.set(tr('저장한 장치가 없습니다. 연결 설정에서 직접 선택하세요.'))
    def open_connection(self):
        if self.connection and self.connection.winfo_exists(): self.connection.lift(); return
        win=tk.Toplevel(self.root); self.connection=win; win.title(tr('연결 설정 · 도움말')); win.configure(bg=CARD); win.geometry('660x660'); win.transient(self.root)
        area=ttk.Frame(win,padding=24); area.pack(fill='both',expand=True)
        ttk.Label(area,text=tr('연결 설정'),font=('맑은 고딕',15,'bold')).pack(anchor='w',pady=(0,15))
        self.conn_widgets={}
        for label,var,values,key in [(tr('입력 · 장치 전체에서 사용'),self.source,self.inputs,'source'),(tr('출력 · DualSense'),self.destination,self.outputs,'output'),(tr('처리할 채널 · 메인 화면과 동일'),self.channel,list(CHANNELS),'channel')]:
            ttk.Label(area,text=label,style='Muted.TLabel').pack(anchor='w',pady=(10,6))
            box=ttk.Combobox(area,values=values,textvariable=var,state='readonly'); box.pack(fill='x'); box.bind('<<ComboboxSelected>>',lambda e:self.render()); self.conn_widgets[key]=box
        self.normal_button=ttk.Radiobutton(area,text=tr('일반 모드'),variable=self.mode,value='normal',command=self.update_controls); self.normal_button.pack(anchor='w',pady=(16,3))
        ttk.Label(area,text=tr('퓨어 모드: 현재 미지원. 기존 퓨어 프리셋은 무음으로 유지됩니다.'),style='Muted.TLabel').pack(anchor='w')
        ttk.Label(area,text=tr('6ch는 전면 L/R을 기본으로 사용하며 센터·후방·LFE를 추가할 수 있습니다.\n2ch는 이미 섞인 좌우 소리라 후방·LFE를 따로 추가할 수 없습니다.\n장치 전체: 실제 6ch 캡처면 5.1채널만, 2ch면 2채널만 선택됩니다.\n자동 장치는 시작 후 캡처 형식을 확인합니다. 게임 설정과 다를 수 있습니다.\n선택 게임: 정지 중 캡처 요청 형식을 직접 선택합니다.\n\nPC 필터 끄기 ≠ 기존 BAT와 같은 입력\n기존 기준: 장치 전체 + 센터/후방/LFE 끔 + PC 필터 끔.\nStudio 필터와 귀로 듣는 원음은 이 화면에서 바꾸지 않습니다.'),style='Muted.TLabel',wraplength=590).pack(anchor='w',pady=15)
        ttk.Button(area,text=tr('닫기'),command=win.destroy).pack(anchor='e'); self.render_connection()
    def render_connection(self):
        active=bool(self.engine)
        for key,w in self.conn_widgets.items():
            enabled=not active and (key=='output' or key=='source' and self.scope.get()=='device' or key=='channel')
            if key=='channel':
                ch=self.capture_channels()
                w.configure(values=[next(k for k,v in CHANNELS.items() if v==ch)] if self.scope.get()=='device' and ch in (2,6) else list(CHANNELS))
                enabled=enabled and (self.scope.get()=='process' or ch in (2,6))
            w.configure(state='readonly' if enabled else 'disabled')
    def start(self):
        if self.games_busy:return
        panel=getattr(self,'studio_window',None)
        if panel is not None and panel.busy:
            self.status.set('Studio '+('작업 완료 후 시작하세요.' if LANGUAGE=='ko' else 'operation in progress. Wait before starting.'));return
        if self.engine: return
        if self.destination.get() not in self.outputs or self.scope.get()=='device' and self.source.get() not in self.inputs:
            messagebox.showerror(tr('장치 선택'),tr('연결 설정에서 입출력 장치를 선택하세요.'),parent=self.root); return
        pid=self.game_map.get(self.game.get()) if self.scope.get()=='process' else None
        if self.scope.get()=='process' and not pid:
            messagebox.showerror(tr('게임 선택'),tr('게임을 실행하고 새로고침 후 실제 게임 exe를 선택하세요.'),parent=self.root); return
        self.update_controls()
        candidate=Engine(None if self.source.get()==AUTO else self.source.get(),None if self.destination.get()==AUTO else self.destination.get(),self.controls,process_pid=pid,process_channels=CHANNELS[self.channel.get()])
        try:
            candidate.start(); self.engine=candidate; self.status.set(tr('연결 중…')); self.render()
        except Exception as exc: messagebox.showerror(tr('시작 실패'),tr(str(exc)),parent=self.root)
    def stop(self):
        if self.engine:
            if not self.engine.stop(): self.status.set(tr('정지 대기 중 · 드라이버 응답을 기다립니다.')); return False
            self.engine=None
        self.status.set(tr('정지')); self.render(); return True
    def tick(self):
        # Reuse this existing timer. Battery workers only run every 5 min.
        panel=getattr(self,'studio_window',None);preferred=self.battery.preferred;panel_busy=False
        if panel is not None and panel.win.winfo_exists():
            panel_busy=panel.busy;d=panel.device.current()
            if 0<=d<len(panel.paths):preferred=panel.paths[d]
        self.battery.tick(paused=self.root.state()=='iconic' or panel_busy or '--smoke-test' in sys.argv,preferred=preferred)
        if self.root.state()!='iconic':
            text=battery_text(self.battery,LANGUAGE)
            if self.battery_label.cget('text')!=text:self.battery_label.configure(text=text)
            self.battery_icon.show(self.battery)
        # No animation or live plots; no hidden/minimized statistics work.
        if self.engine and self.root.state()!='iconic':
            self.status.set(tr(self.engine.status)); self.render()
        self.root.after(1000,self.tick)


def smoke(app,report):
    from types import SimpleNamespace
    results={"default_limiter_hard":app.controls.limiter=="hard", "channel_order": [w.cget("text") for w in app.channel_labels]==[tr("후방 L / R"),tr("센터 · 대사도 포함"),tr("LFE 저음")]}
    app.scope.set('process'); app.channel.set(list(CHANNELS)[0]); app.center.set(True); app.rear.set(True); app.lfe.set(True); app.filter_on.set(True); app.strength.set(73); app.limiter.set(tr('초과분 자르기')); app.update_controls()
    results['six_channel_enabled']=all(s.enabled for s in app.mix_switches) and str(app.limiter_box['state'])=='readonly'
    app.filter_switch.invoke()
    results['filter_off_maps_to_bypass']=app.controls.bypass and all(str(w['state'])=='disabled' for w in app.filter_widgets) and app.controls.rear and app.controls.lfe
    app.filter_switch.invoke()
    results['filter_on_maps_to_processing']=not app.controls.bypass
    app.channel.set(list(CHANNELS)[1]); app.render()
    app.mix_switches[0].invoke()
    results['center_enabled_six']=len(app.mix_switches)==3 and app.controls.center
    results['two_channel_disabled']=all(not s.enabled for s in app.mix_switches) and str(app.limiter_box['state'])=='disabled' and app.rear.get() and app.center.get() and not app.controls.bypass
    app.device_channel_cache.clear(); app.channel.set(list(CHANNELS)[0]); app.scope.set('device'); app.source.set(AUTO); app.render()
    results['unknown_device_five_one_configurable']=all(s.enabled for s in app.mix_switches) and app.capture_channels() is None
    app.engine=SimpleNamespace(capture_channels=2); app.render()
    results['actual_device_two_disabled']=all(not s.enabled for s in app.mix_switches)
    app.engine.capture_channels=6; app.render()
    results['actual_device_six_enabled']=all(s.enabled for s in app.mix_switches)
    app.engine=None; app.scope.set('process'); app.channel.set(list(CHANNELS)[0]); app.update_controls()
    if '--preset-test-path' in sys.argv:
        app.slot_name.set(tr('UI 시험')); app.desired_game='test_game.exe'; app.save_slot()
        app.filter_on.set(False); app.strength.set(12); app.center.set(False); app.rear.set(False); app.lfe.set(False); app.limiter.set(tr('부드러운 제한')); app.update_controls(); app.load_slot()
        results['preset_roundtrip']=app.filter_on.get() and app.strength.get()==73 and app.rear.get() and app.lfe.get() and app.center.get() and app.controls.center and app.controls.limiter=='hard' and app.desired_game=='test_game.exe'
    app.toggle_details(); app.root.update_idletasks()
    clipped=[]
    def bounds(widget):
        for child in widget.winfo_children():
            if child.winfo_viewable() and not isinstance(child,tk.Toplevel):
                x=child.winfo_rootx()-app.root.winfo_rootx(); y=child.winfo_rooty()-app.root.winfo_rooty()
                if x<0 or y<0 or x+child.winfo_width()>app.root.winfo_width()+1 or y+child.winfo_height()>app.root.winfo_height()+1:
                    clipped.append(str(child))
                bounds(child)
    bounds(app.root)
    results['widgets_outside_window']=clipped
    app.open_connection(); app.root.update_idletasks()
    app.scope.set('process'); app.render()
    results['process_connection_fields']=str(app.conn_widgets['source']['state'])=='disabled' and str(app.conn_widgets['channel']['state'])=='readonly'
    app.scope.set('device'); app.render()
    results['device_connection_fields']=str(app.conn_widgets['source']['state'])=='readonly' and str(app.conn_widgets['channel']['state'])=='readonly'
    app.connection.destroy(); app.connection=None
    results.update(language=LANGUAGE,controls=asdict(app.controls),tk_window_created=True,audio_started=False,width=app.root.winfo_width(),height=app.root.winfo_height(),requested_height=app.root.winfo_reqheight(),inputs=app.inputs,outputs=app.outputs,preset_slots=SLOT_COUNT)
    app.open_studio(); app.root.update_idletasks()
    panel=app.studio_window
    results['process_sort_options']=set(PROCESS_SORT.values())=={'name','cpu'}
    results['battery_label_present']=app.battery_label.winfo_exists()==1
    results['studio_panel_embedded']=panel.embedded and not isinstance(panel.win,tk.Toplevel)
    results['studio_strength_order']=panel.strength_order==['gain','intensity','trigger']
    results['battery_icon_present']=app.battery_icon.winfo_exists()==1
    results['studio_dialog_fits']=panel.win.winfo_reqheight()<=panel.win.winfo_height()
    required=[app.start_button,app.stop_button,app.details_button,app.order_box,app.battery_icon,panel.status_label,panel.choice,panel.intensity_scale]+[e['scale'] for e in panel.extra.values()]
    results['required_controls_visible']=all(w.winfo_ismapped() and w.winfo_height()>=w.winfo_reqheight() and w.winfo_width()>10 for w in required)
    results['natural_height_fits']=app.root.winfo_reqheight()<=app.root.winfo_height()
    results['studio_extra_initially_disabled']=all(str(e['apply']['state'])=='disabled' for e in panel.extra.values())
    results['studio_strength_initially_disabled']=str(panel.intensity_apply['state'])=='disabled'
    results['studio_apply_initially_disabled']=str(panel.apply['state'])=='disabled'
    import hid
    results['hid_module_available']=hasattr(hid,'device')
    report.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results


def main():
    root=tk.Tk(); lock=None
    try:
        lock=InstanceLock(); app=App(root)
    except Exception as exc:
        if '--smoke-test' in sys.argv:
            Path(sys.argv[sys.argv.index('--smoke-test')+1]).write_text(json.dumps({'error':str(exc)},ensure_ascii=False),encoding='utf-8')
        else: messagebox.showerror(tr('실행 실패'),tr(str(exc)),parent=root)
        if lock: lock.close()
        root.destroy(); return
    def close():
        if app.studio_window.busy:
            app.status.set('Studio 작업 완료 후 종료하세요.' if LANGUAGE=='ko' else 'Wait for the Studio operation before closing.');return
        if app.stop(): app.save_session(); lock.close(); root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    if '--smoke-test' in sys.argv:
        report=Path(sys.argv[sys.argv.index('--smoke-test')+1])
        def run_smoke():
            try: smoke(app,report)
            except Exception as exc: report.write_text(json.dumps({'error':str(exc)},ensure_ascii=False),encoding='utf-8')
            finally: close()
        root.after(2000,run_smoke)
    if '--silent-probe-report' in sys.argv:
        report=Path(sys.argv[sys.argv.index('--silent-probe-report')+1])
        def begin_probe():
            try:
                app.engine=Engine(controls=Controls(bypass=True),silent=True); app.engine.start()
                root.after(8000,end_probe)
            except Exception as exc:
                report.write_text(json.dumps({'error':str(exc)},ensure_ascii=False),encoding='utf-8'); close()
        def end_probe():
            if app.engine:
                app.engine.stop(); report.write_text(json.dumps(app.engine.stats(),ensure_ascii=False,indent=2),encoding='utf-8')
            close()
        root.after(100,begin_probe)
    if '--process-probe-report' in sys.argv:
        report=Path(sys.argv[sys.argv.index('--process-probe-report')+1])
        def process_probe():
            import time
            from process_audio import ProcessCaptureStream
            stream=None
            try:
                stream=ProcessCaptureStream(os.getpid(),6); until=time.perf_counter()+2; frames=0
                while time.perf_counter()<until:
                    if stream.get_read_available()>=480: stream.read(480); frames+=480
                    else: time.sleep(.001)
                result=dict(process_api_opened=True,frames=frames,channels=6,drops=stream.drops,stale=stream.stale,dongle_output=False,audio_recorded=False)
            except Exception as exc: result=dict(error=str(exc))
            finally:
                if stream: stream.close()
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); close()
        root.after(100,process_probe)
    root.mainloop()

if __name__=='__main__': main()
