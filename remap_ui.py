"""On-demand native Tk macro editor; no background input monitoring."""
from ps_policy import ps_rows
from pathlib import Path
import queue
import threading
import time
from collections import deque
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from remap_connection import Applied, apply_connected, apply_common_connected
from key_capture import KeyCapture, event_key
from remap_state import has_pending_edits
from ui_viewport import place_popup, message_area
from remapping import BUTTONS, OUTPUTS, EMPTY, describe, editable, make_record, keys_text, device_operation, make_swipe, is_swipe, SWIPE_DIRECTIONS, easy_swipe

OUTPUT_LABELS={'×':'✕','Keyboard':'키보드','Mouse left':'마우스 왼쪽 클릭','Mouse right':'마우스 오른쪽 클릭',
    'Mouse middle':'마우스 휠 클릭','Wheel up':'휠 위로','Wheel down':'휠 아래로',
    'Touchpad':'터치패드 클릭','Create':'공유 버튼','Options':'옵션 버튼'}

def history_lines(names,measure,width,rows=4):
    lines=[];line=''
    for name in names:
        label=name
        while measure(label)>width and len(label)>1:label=label[:-2]+'…'
        candidate=line+'  ·  '+label if line else label
        if line and measure(candidate)>width:lines.append(line);line=label
        else:line=candidate
    if line:lines.append(line)
    return lines[-rows:]

class OutputChoice(ttk.Combobox):
    """Readable labels while keeping protocol names stable."""
    def __init__(self,parent,**kwargs):
        kwargs['values']=[OUTPUT_LABELS.get(v,v) for v in OUTPUTS]
        super().__init__(parent,**kwargs)
    def get(self):
        label=super().get()
        return next((key for key,value in OUTPUT_LABELS.items() if value==label),label)
    def set(self,value):super().set(OUTPUT_LABELS.get(value,value))

class RemapPanel:
    def __init__(self,app,parent):
        self.app=app;self.busy=False;self.snapshot=None;self.edit_baseline=None;self.path=None
        self.rows=[EMPTY]*32;self.disabled=0xffffffff;self.results=queue.Queue()
        from remap_presets import RemapPresets
        self.preset_store=RemapPresets(app.store.path.parent/'remap_presets.json')
        self.gesture=0;self.preview_mask=0;self.preview_timer=None
        from input_preview import InputPreview
        self.preview=InputPreview();self.device_preview=self.preview;self.preview_mode='device'
        from keyboard_preview import KeyboardPreview
        self.keyboard_preview=KeyboardPreview();self.recent_inputs=deque(maxlen=32);self.history_drawn=None;self.keyboard_notice=''
        self.swipe_group=None;self.dialogs={}
        self.selected_button=5;self.capture=KeyCapture();self.pending_keyboard=False
        self.frame=ttk.Frame(parent,padding=6);self.frame.pack(fill='both',expand=True)
        self.status=tk.StringVar(value='Pico 2 W에서 읽은 후 패드의 버튼을 선택하세요.')
        self.enabled=tk.BooleanVar(value=True);self.hold=tk.BooleanVar(value=True);self.replace=tk.BooleanVar(value=True)
        self.common_apply=tk.BooleanVar();self.progress=queue.Queue()
        self.ps_enabled=tk.BooleanVar();self.keys=tk.StringVar();self.label=tk.StringVar()
        self.inputs=[tk.BooleanVar() for _ in BUTTONS]
        self.selection_title=tk.StringVar(value='× 버튼')
        self.mapping_summary=tk.StringVar(value='기본 동작')
        self.preset_index=0;self.preset_name=tk.StringVar(value='프리셋 1')
        shell=ttk.Frame(self.frame);shell.pack(fill='both',expand=True)
        sidebar=ttk.Frame(shell,width=156,padding=(0,4,8,0));sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
        ttk.Label(sidebar,text='PC 프리셋',font=('맑은 고딕',13,'bold')).pack(anchor='w',pady=(0,16))
        self.preset_buttons=[]
        for i in range(4):
            b=ttk.Button(sidebar,command=lambda j=i:self.choose_preset(j));b.pack(fill='x',pady=5);self.preset_buttons.append(b)
        ttk.Separator(sidebar).pack(fill='x',pady=16)
        ttk.Entry(sidebar,textvariable=self.preset_name).pack(fill='x')
        self.save_preset_button=ttk.Button(sidebar,text='이 프리셋에 저장',command=self.save_preset);self.save_preset_button.pack(fill='x',pady=(8,5))
        ttk.Label(sidebar,text='이 PC에 4개 저장\n불러오기만으로 Pico 2 W에\n적용되지 않습니다.',style='Muted.TLabel').pack(anchor='w',pady=14)
        main=ttk.Frame(shell);main.pack(side='left',fill='both',expand=True)
        header=ttk.Frame(main);header.pack(fill='x')
        ttk.Label(header,text='버튼 리매핑',font=('맑은 고딕',18,'bold')).pack(side='left')
        self.read_button=ttk.Button(header,text='리맵 다시 읽기',command=self.read);self.read_button.pack(side='right')
        ttk.Button(header,text='도움말',command=self.help).pack(side='right',padx=6)
        self.preview_button=tk.Button(header,text='입력 테스트 시작',command=self.toggle_preview,width=18,font=('맑은 고딕',9),background='#263445',foreground='white',activebackground='#35475c',activeforeground='white',relief='flat',padx=10,pady=4);self.preview_button.pack(side='right')
        self.controller_image=tk.PhotoImage(file=str(Path(__file__).parent/'assets'/'dualsense-ui.png'))
        self.history_font=tkfont.Font(root=self.frame,family='Segoe UI Symbol',size=11,weight='bold')
        self.pad=tk.Canvas(main,height=340,bg='#18212e',highlightthickness=0)
        self.pad.bind('<Button-1>',self.pad_click)
        self.frame.bind('<Unmap>',lambda e:self.stop_preview() if e.widget is self.frame else None)
        self.frame.bind('<Destroy>',lambda e:self.stop_preview() if e.widget is self.frame else None)
        self.pad.bind('<Motion>',self.pad_hover)
        self.pad.pack(fill='x',pady=(4,2));self.pad.bind('<Configure>',self.draw_pad)
        self.pad.bind('<Left>',lambda e:self.choose_button((self.selected_button-1)%len(BUTTONS)))
        self.pad.bind('<Right>',lambda e:self.choose_button((self.selected_button+1)%len(BUTTONS)))
        self.pad.configure(takefocus=True)
        self.mapping_hint=ttk.Label(main,text='현재 적용 동작 → 변경할 동작* · 적용 후에는 새 동작만 표시',wraplength=700,width=1,anchor='center');self.mapping_hint.pack(fill='x')
        self.preview_hint=ttk.Label(message_area(main,3),text='패드의 버튼을 클릭하여 아래에서 설정하세요.',style='Muted.TLabel',anchor='center',wraplength=700,width=1);self.preview_hint.pack(fill='x',pady=(0,6))
        editor=ttk.Frame(main,padding=5);self.editor=editor;editor.pack(fill='x')
        heading=ttk.Frame(editor);heading.pack(fill='x')
        ttk.Label(heading,textvariable=self.selection_title,font=('맑은 고딕',15,'bold'),wraplength=520).pack(side='left')
        ttk.Label(heading,text='  →  ',foreground='#82e5cc').pack(side='left')
        ttk.Label(heading,textvariable=self.mapping_summary,foreground='#82e5cc',wraplength=200).pack(side='left')
        fields=ttk.Frame(editor);fields.pack(fill='x',pady=(10,6))
        ttk.Label(fields,text='이 버튼을 누르면').grid(row=0,column=0,sticky='w',padx=(0,14))
        self.output=OutputChoice(fields,state='readonly',width=18);self.output.set('Keyboard');self.output.grid(row=0,column=1,sticky='ew')
        self.output.bind('<<ComboboxSelected>>',lambda e:self.output_selected())
        self.key_entry=ttk.Entry(fields,textvariable=self.keys,width=24,state='readonly',takefocus=True);self.key_entry.grid(row=0,column=2,sticky='ew',padx=10)
        fields.columnconfigure(2,weight=1)
        self.key_entry.bind('<Button-1>',lambda e:self.key_entry.focus_set())
        self.key_entry.bind('<KeyPress>',self.capture_press)
        self.key_entry.bind('<KeyRelease>',self.capture_release)
        self.key_entry.bind('<FocusOut>',self.capture_blur)
        ttk.Button(fields,text='특수키·숫자패드',command=self.key_picker).grid(row=0,column=3)
        self.key_hint=ttk.Label(editor,text='키보드 조합: CTRL+SHIFT+A · 최대 4키',style='Muted.TLabel');self.key_hint.pack(anchor='w')
        options=ttk.Frame(editor);options.pack(fill='x',pady=6)
        modes=ttk.Frame(options);modes.pack(fill='x',pady=(0,6))
        ttk.Label(modes,text='추가 기능').pack(side='left',padx=(0,12))
        self.action_mode=tk.StringVar(value='기본 키 지정')
        self.mode_choice=ttk.Combobox(modes,textvariable=self.action_mode,values=('기본 키 지정','패드 키 조합','키보드 조합'),state='readonly',width=28);self.mode_choice.pack(side='left')
        self.mode_choice.bind('<<ComboboxSelected>>',lambda e:self.action_changed())
        self.keep_original=ttk.Checkbutton(options,text='원래 버튼도 함께 누르기',variable=self.replace,onvalue=False,offvalue=True,command=self.edit)
        self.keep_original.pack(anchor='w')
        ttk.Label(options,text='예: ×를 A로 바꾼 경우, 체크하면 ×와 A가 함께 입력됩니다.',style='Muted.TLabel').pack(anchor='w',pady=(3,0))
        actions=ttk.Frame(editor);actions.pack(fill='x')
        ttk.Button(actions,text='기본 동작으로 초기화',command=self.clear).pack(side='left')
        from ui_help import help_icon
        help_icon(actions,'선택한 버튼 또는 스와이프의 리맵만 지웁니다. 전체 초기화가 아닙니다.\nPico 2 W에 적용을 눌러야 장치에 반영됩니다.')
        ttk.Button(actions,text='여러 패드 버튼 함께 누르기',command=self.chord_picker).pack(side='left',padx=8)
        ttk.Button(actions,text='설정 목록',command=self.toggle_advanced).pack(side='left',padx=8)
        from xbox_turbo import SourceTurboPanel
        self.turbo_panel=SourceTurboPanel(app,main,self)
        # Advanced rows and chord inputs are available on demand, outside the main layout.
        self.advanced=None
        self.table=ttk.Treeview(main,columns=('on','input','output'),show='headings',height=8,selectmode='browse')
        for key,title,width in [('on','켜짐',55),('input','입력',220),('output','출력',160)]:
            self.table.heading(key,text=title);self.table.column(key,width=width)
        # Selection is explicit; hidden tree has no queued selection callback.
        ps_row=ttk.Frame(main);ps_row.pack(anchor='w',pady=(6,4))
        self.ps_check=ttk.Checkbutton(ps_row,text='Studio PS 단축키 사용',variable=self.ps_enabled,command=self.ps_changed);self.ps_check.pack(side='left')
        from ui_help import help_icon
        self.ps_help=help_icon(ps_row,'켜면 Studio의 PS 버튼 조합 단축키를 사용하며, PS 버튼 리맵은 비활성화됩니다.\n기존 리맵 내용은 보존됩니다. 체크를 해제해도 자동으로 다시 활성화하지 않습니다.\n변경은 적용 버튼을 눌러 장치에 반영하세요.')
        self.common_check=ttk.Checkbutton(main,text='모든 장치 프로필에 같은 버튼 설정 저장',variable=self.common_apply,command=self.common_changed);self.common_check.pack(anchor='w')
        bottom=ttk.Frame(main);self.bottom=bottom;bottom.pack(fill='x',pady=4)
        self.revert_button=ttk.Button(bottom,text='편집 취소',command=self.revert);self.revert_button.pack(side='left')
        ttk.Button(bottom,text='모든 버튼 기본값으로',command=self.reset_all).pack(side='left',padx=8)
        apply_bar=ttk.Frame(main);apply_bar.pack(fill='x',pady=3)
        self.apply_button=ttk.Button(apply_bar,text='Pico에 저장',command=self.apply,style='Accent.TButton');self.apply_button.pack(side='right')
        self.temporary_button=ttk.Button(apply_bar,text='임시 적용',command=lambda:self.apply(temporary=True),style='Accent.TButton');self.temporary_button.pack(side='right',padx=5)
        self.restore_temporary_button=None;self.retry_save_button=None
        self.troubleshoot_button=ttk.Button(apply_bar,text='리맵 문제 해결',command=self.remap_troubleshoot);self.troubleshoot_button.pack(side='left')
        self.status_label=ttk.Label(message_area(main,3),textvariable=self.status,wraplength=700,width=1,style='Muted.TLabel');self.status_label.pack(fill='x',pady=4)
        main.bind('<Configure>',self.wrap_messages,add='+')
        self.refresh();self.refresh_presets();self.choose_button(5)
        self.frame.bind('<Map>',lambda e:self.update_availability() if e.widget is self.frame else None)
        self.update_availability()
    def remap_troubleshoot(self):
        win=self.dialog('remap_troubleshoot','리맵 문제 해결')
        if win is None:return
        box=ttk.Frame(win,padding=14);box.pack(fill='both',expand=True)
        ttk.Label(box,text='평소에는 임시 적용 / Pico에 저장만 사용하세요.',font=('맑은 고딕',11,'bold')).pack(anchor='w',pady=(0,12))
        sections=[('임시 적용 전으로 되돌리기',
            '임시 설정을 취소하고 싶거나, 종료·연결 끊김 후 원래 설정으로 돌아오지 않았을 때 사용합니다. 정상 종료 시에는 자동으로 복원합니다.',
            self.restore_temporary,'restore_temporary_button'),
            ('실패한 Pico 저장 다시 시도',
            'Pico 저장 도중 오류가 나거나 완료 여부를 확인하지 못했을 때 사용합니다. 현재 화면 편집값이 아닌, 실패 당시 저장하려던 설정을 다시 저장합니다.',
            self.retry_saved_remap,'retry_save_button')]
        for title,description,command,attr in sections:
            frame=ttk.LabelFrame(box,text=title,padding=10);frame.pack(fill='x',pady=5)
            ttk.Label(frame,text=description,wraplength=430).pack(anchor='w')
            button=ttk.Button(frame,text=title,command=command);button.pack(anchor='w',pady=(7,0));setattr(self,attr,button)
        ttk.Label(box,text='Pico를 연결한 뒤 사용하세요. 다른 설정으로 바뀌었다면 덮어쓰지 않고 중단합니다.',wraplength=450).pack(anchor='w',pady=8)
        ttk.Label(box,textvariable=self.status,wraplength=450).pack(fill='x',pady=8)
        def open_logs():
            try:
                import os
                from remap_diagnostics import folder
                path=folder();path.mkdir(parents=True,exist_ok=True);os.startfile(str(path))
            except Exception as exc:self.status.set('로그 폴더 열기 실패: '+str(exc))
        ttk.Button(box,text='로그 폴더 열기',command=open_logs).pack(anchor='w')
        ttk.Label(box,text='리맵 기록: remap.log · 단계별 소요 시간과 오류 기록',style='Muted.TLabel').pack(anchor='w',pady=(4,0))
        self.update_availability(force=True)

    def wrap_messages(self,event):
        width=max(120,event.width-8)
        for label in (self.mapping_hint,self.preview_hint,self.status_label):
            if int(label.cget('wraplength'))!=width:label.configure(wraplength=width)
    def draw_pad(self,event=None):
        p=self.pad;p.delete('all');ox=(p.winfo_width()-self.controller_image.width())/2
        p.create_image(ox,0,image=self.controller_image,anchor='nw')
        positions={'↑':(113,78,18,18),'↓':(113,138,18,18),'←':(83,109,18,18),'→':(144,109,18,18),
            '□':(412,109,20,20),'×':(448,145,20,20),'○':(483,109,20,20),'△':(448,73,20,20),
            'Create':(157,55,11,18),'Options':(402,55,11,18),'Touchpad':(280,71,96,50),
            'L3':(196,184,36,36),'R3':(365,184,36,36),'PS':(280,175,18,18),'Mute':(280,212,18,10),
            'L2':(-32,24,25,15),'L1':(-32,65,25,15),'R2':(592,24,25,15),'R1':(592,65,25,15)}
        self.hit_regions=[]
        for i,name in enumerate(BUTTONS):
            x,y,rx,ry=positions[name];x+=ox;self.hit_regions.append((x,y,rx,ry))
            label=self.button_display(i)
            dirty=self.button_caption(i)[2]
            bw=36 if name in ('Touchpad','Create','Options','Mute') else 23 if name in ('L1','L2','R1','R2') else 17
            if len(label)>12 and ' → ' in label:
                before,after=label.split(' → ',1)
                shown=(before if len(before)<=8 else before[:7]+'…')+' →\n'+(after if len(after)<=8 else after[:7]+'…')
            else:shown=label if len(label)<=12 else label[:11]+'…'
            longest=max(len(line) for line in shown.split('\n'))
            if longest>2:bw=max(bw,min(48,longest*5+6))
            bh=19 if '\n' in shown else 12
            selected=self.inputs[i].get();blocked=i==16 and self.ps_enabled.get()
            p.create_rectangle(x-bw,y-bh,x+bw,y+bh,fill='#151b25' if blocked else '#bb7624' if self.preview_mask&(1<<i) else '#294f53' if selected else '#202c3b',outline='#44505e' if blocked else '#82e5cc' if selected else '#8899af',width=2 if selected else 1,tags=(f'button-{i}',))
            p.create_text(x,y,text=shown,fill='#596573' if blocked else '#f0bd6c' if dirty else '#7d8795' if not self.edit_available() else '#b4f4e1' if selected else '#eef4ff',font=('Segoe UI Symbol',14 if shown in ('✕','□','△','○') else 9,'bold'),tags=('mapping-label',f'mapping-{i}'))
            # Label boxes and visible button centres are both clickable.
            self.hit_regions[-1]=(x,y,max(rx,bw),max(ry,bh))
        self.draw_swipes()
        if hasattr(self,'mapping_hint'):
            self.mapping_hint.configure(text=('장치에서 읽은 설정 · ' if self.snapshot else '장치 설정 미확인 · 다시 읽으세요. ')+ '현재 적용 동작 → 변경할 동작* · * 아직 적용하지 않은 변경')
        self.draw_history(force=True)
    def draw_history(self,force=False):
        now=time.monotonic()
        while self.recent_inputs and now-self.recent_inputs[0][0]>=2.5:self.recent_inputs.popleft()
        values=tuple(self.recent_inputs)
        if not force and values==self.history_drawn:return
        self.history_drawn=values;p=self.pad;p.delete('history')
        if not values:return
        width=220;x=max(6,p.winfo_width()-width-6);y=118
        lines=history_lines([name for _,name in values],self.history_font.measure,width-20)
        p.create_rectangle(x,y,x+width,y+116,fill='#202c3b',outline='#445469',tags='history')
        p.create_text(x+10,y+14,text='최근 입력',anchor='w',fill='#82e5cc',tags='history')
        for i,line in enumerate(lines):p.create_text(x+10,y+38+i*22,text=line,anchor='w',fill='#eef4ff',font=self.history_font,tags='history')
    def pad_hit(self,event):
        for i,(x,y,rx,ry) in enumerate(getattr(self,'hit_regions',[])):
            if abs(event.x-x)<=rx and abs(event.y-y)<=ry:return i
    def pad_click(self,event):
        gesture=self.swipe_hit(event)
        if gesture is not None and self.edit_available():self.select_swipe(gesture);return
        i=self.pad_hit(event)
        if i==16 and self.ps_enabled.get():return
        if i is not None and self.edit_available():self.pad.focus_set();self.choose_button(i)
    def pad_hover(self,event):
        button=self.pad_hit(event);gesture=self.swipe_hit(event)
        if gesture is not None and hasattr(self,'mapping_hint'):
            self.mapping_hint.configure(text=('오른쪽' if gesture&4 else '왼쪽')+' '+SWIPE_DIRECTIONS[gesture&3]+' 스와이프 → '+self.swipe_value(gesture))
        elif button is not None and hasattr(self,'mapping_hint'):
            original,value,dirty=self.button_caption(button)
            self.mapping_hint.configure(text=self.button_display(button)+(' · 아직 적용하지 않음' if dirty else ' · 읽은/적용한 설정' if self.snapshot else ' · 장치 설정 미확인'))
        self.pad.configure(cursor='hand2' if self.edit_available() and not (button==16 and self.ps_enabled.get()) and (button is not None or gesture is not None) else '')
    def mode_changed(self):
        self.hold.set(True)
        pulse=bool(self.gesture) or self.action_mode.get()=='키를 순서대로 한 번 입력'
        self.keep_original.configure(state='disabled' if pulse else 'normal')
    def button_label(self,button):
        original={'×':'✕','Mute':'음소거','Touchpad':'터치패드','Create':'공유','Options':'옵션'}.get(BUTTONS[button],BUTTONS[button])
        rows=[r for i,r in enumerate(self.rows) if not self.disabled&(1<<i) and int.from_bytes(r[:4],'little')==(1<<button)]
        if len(rows)==1 and editable(rows[0]):
            value=describe(rows[0])[1]
            return OUTPUT_LABELS.get(value,value)
        return original
    def button_value(self,rows,mask,button):
        original={'×':'✕','Mute':'음소거','Touchpad':'터치패드','Create':'공유','Options':'옵션'}.get(BUTTONS[button],BUTTONS[button])
        active=tuple(r for i,r in enumerate(rows) if not mask&(1<<i) and int.from_bytes(r[:4],'little')&(1<<button))
        if not active:return original,None,active
        if len(active)>1:
            from pad_combo import valid_group
            if valid_group(active):return original,('' if active[0][5]&4 else original+' + ')+' + '.join(describe(r)[1] for r in active),active
            return original,'여러 동작',active
        row=active[0]
        if not editable(row):return original,'고급 매크로',active
        value=OUTPUT_LABELS.get(describe(row)[1],describe(row)[1])
        if int.from_bytes(row[:4],'little')!=(1<<button):value=describe(row)[0]+' → '+value
        elif not row[5]&4:value=original+' + '+value
        return original,value,active
    def button_caption(self,button):
        original,value,active=self.button_value(self.rows,self.disabled,button)
        baseline=self.snapshot or self.edit_baseline
        previous=self.button_value(baseline.rows,baseline.disabled,button)[2] if baseline else ()
        return original,value,active!=previous
    def button_display(self,button):
        original,value,dirty=self.button_caption(button);current=value or original
        if not dirty:return current
        baseline=self.snapshot or self.edit_baseline
        if baseline:
            old_original,old_value,_=self.button_value(baseline.rows,baseline.disabled,button)
            previous=old_value or old_original
        else:previous='미확인'
        return previous+' → '+current+'*'

    def output_selected(self):
        if self.action_mode.get()=='패드 키 조합':self.action_mode.set('기본 키 지정')
        self.pending_keyboard=self.output.get()=='Keyboard' and not self.keys.get()
        self.output_changed()
        if self.output.get()!='Keyboard' or self.keys.get():self.edit()
        else:
            self.status.set('입력칸을 클릭하고 지정할 키를 누르세요. 장치에는 아직 적용되지 않습니다.')
            self.key_entry.focus_set()
        self.update_availability(force=True)
    def capture_pad_combo(self):
        try:
            self.local_ready()
            if self.gesture:raise ValueError('패드 키 조합은 한 개의 패드 버튼에 지정하세요.')
            if self.app.engine and self.xbox_test_worker() is None:raise ValueError('입력 등록 전 오디오햅틱을 정지하세요. 조합 편집 후 다시 시작할 수 있습니다.')
            from pad_combo import PAD,stage
            chord=sum(1<<j for j,v in enumerate(self.inputs) if v.get())
            if chord.bit_count()!=1:raise ValueError('조합을 실행할 버튼 한 개를 선택하세요.')
            existing=self.dialogs.get('pad_combo')
            if existing and existing.winfo_exists():existing.lift();return
            win=tk.Toplevel(self.app.root);self.dialogs['pad_combo']=win;win.title('패드 키 조합 입력');win.transient(self.app.root);win.grab_set()
            area=ttk.Frame(win,padding=16);area.pack(fill='both',expand=True)
            ttk.Label(area,text='원하는 패드 버튼들을 눌러 등록하세요. 3~4개 이상도 가능합니다.\n현재 PC에 전달되는 버튼을 모읍니다. 기존 리맵 결과가 반영될 수 있습니다.').pack(anchor='w')
            value=tk.StringVar(value='입력 받기를 누르세요.');ttk.Label(area,textvariable=value,wraplength=480).pack(fill='x',pady=12)
            collected=[];state={'timer':None,'listening':False,'armed':False,'binding':None,'armed_at':None,'preview':None,'thread':None,'deadline':None}
            capture_path=self.target()
            def valid_capture(require_input=True):
                from xbox_settings_job import validate
                if not state['listening'] or self.target()!=capture_path or self.preview_timer is None:raise RuntimeError('입력 등록이 중단됐습니다. 장치 연결을 확인하고 다시 입력 받기를 누르세요.')
                validate(self.app,state['binding'])
                if self.preview is not state['preview'] or self.preview.thread is not state['thread']:raise RuntimeError('입력 연결이 다시 시작됐습니다. 다시 입력 받기를 누르세요.')
                if self.preview.thread is not None and not self.preview.thread.is_alive():raise RuntimeError('패드 입력 연결이 끊겼습니다. 다시 입력 받기를 누르세요.')
                if not state['armed'] and time.monotonic()>state['deadline']:raise RuntimeError('입력 대기 시간이 지났습니다. 버튼을 모두 떼고 다시 입력 받기를 누르세요.')
                if require_input and self.preview_mode!='xbox' and (self.preview.last_received is None or time.monotonic()-self.preview.last_received>1.5):raise RuntimeError('새 패드 입력이 없습니다. 연결을 확인하고 다시 입력 받기를 누르세요.')
            def collect_event(name,stamp):
                name='×' if name=='✕' else name
                if state['listening'] and state['armed'] and stamp>=state['armed_at'] and name in PAD and name not in collected:collected.append(name)
            def stop():
                if state['timer'] is not None:win.after_cancel(state['timer']);state['timer']=None
                if state['listening']:self.stop_preview()
                state['listening']=False
                if getattr(self,'pad_combo_capture_event',None) is collect_event:self.pad_combo_capture_event=None
            def close():stop();win.destroy();self.choose_button(self.selected_button)
            def poll():
                state['timer']=None
                if self.app.closing or not win.winfo_exists():stop();return
                try:valid_capture(require_input=state['armed'])
                except Exception as exc:stop();value.set(str(exc));return
                mask=self.preview.state[0]
                if not state['armed']:
                    if mask==0 and self.preview.last_received is not None:state['armed']=True;state['armed_at']=time.monotonic()
                else:
                    for j,name in enumerate(BUTTONS):
                        if mask&(1<<j) and name in PAD and name not in collected:collected.append(name)
                value.set(' + '.join(collected) if collected else '버튼을 모두 뗀 뒤 원하는 버튼을 누르세요.')
                state['timer']=win.after(30,poll)
            def start():
                stop();collected.clear();state['armed']=False
                self.stop_preview();self.toggle_preview()
                if self.preview_timer is None:value.set(self.status.get());return
                from xbox_settings_job import bind
                state['binding']=bind(self.app);state['preview']=self.preview;state['thread']=self.preview.thread;state['deadline']=time.monotonic()+15;state['listening']=True;self.pad_combo_capture_event=collect_event;poll()
            def save():
                try:
                    self.local_ready();valid_capture();rows,mask=stage(self.rows,self.disabled,chord,collected,not self.replace.get())
                    stop();self.rows,self.disabled=rows,mask;self.refresh();win.destroy();self.choose_button(self.selected_button)
                    self.status.set('패드 키 조합을 준비했습니다. 임시 적용 또는 Pico에 저장을 누르세요.')
                except Exception as exc:value.set(str(exc))
            buttons=ttk.Frame(area);buttons.pack(fill='x')
            ttk.Button(buttons,text='입력 받기 / 다시 받기',command=start).pack(side='left')
            ttk.Button(buttons,text='조합 선택 완료',command=save).pack(side='right')
            ttk.Button(buttons,text='취소',command=close).pack(side='right',padx=6)
            win.protocol('WM_DELETE_WINDOW',close);place_popup(win,self.app.root)
        except Exception as exc:self.status.set(str(exc));self.choose_button(self.selected_button)

    def action_changed(self):
        if self.action_mode.get()=='패드 키 조합':
            self.capture_pad_combo();return
        if self.action_mode.get()=='키보드 조합':
            self.output.set('Keyboard');self.output_changed()
            self.pending_keyboard=not bool(self.keys.get())
            if self.keys.get():
                if self.edit() and not self.gesture:self.action_mode.set('키보드 조합')
            else:self.status.set('예: CTRL과 Q를 함께 누른 뒤 떼세요. 최대 4키를 지정할 수 있습니다.')
            self.mode_changed();self.update_availability(force=True);self.key_entry.focus_set()
            return
        if self.output.get()!='Keyboard' or self.keys.get():self.edit()
        self.mode_changed()
        if self.action_mode.get()=='키를 순서대로 한 번 입력':
            self.status.set('지정한 키를 순서대로 누르고 해제하는 1회 동작입니다(최대 4키). 시간 간격·반복 편집은 지원하지 않습니다. 원래 패드 버튼도 전달됩니다.')
    def chord_picker(self):
        win=self.dialog('chord','여러 패드 버튼 함께 누르기')
        if win is None:return
        box=ttk.Frame(win,padding=16);box.pack()
        ttk.Label(box,text='예: L1과 ✕를 함께 눌렀을 때만 실행할 동작을 추가합니다.\n키보드 CTRL+Q 같은 출력 조합은 아래의 [키보드 조합]에서 지정하세요.').grid(row=0,column=0,columnspan=5,pady=10)
        selected=[tk.BooleanVar(value=i==self.selected_button) for i in range(len(BUTTONS))]
        for i,name in enumerate(BUTTONS):
            ttk.Checkbutton(box,text=OUTPUT_LABELS.get(name,{'Mute':'음소거'}.get(name,name)),variable=selected[i]).grid(row=1+i//5,column=i%5,sticky='w',padx=8,pady=5)
        def choose():
            chord=sum(1<<i for i,v in enumerate(selected) if v.get())
            if chord.bit_count()<2:self.status.set('함께 누를 패드 버튼을 2개 이상 선택하세요.');return
            if not self.choose_trigger(chord,0):return
            self.selection_title.set('+'.join(n for i,n in enumerate(BUTTONS) if chord&(1<<i)))
            win.destroy();self.status.set('이 버튼들을 함께 눌렀을 때의 동작을 아래에서 지정하세요.')
        ttk.Button(box,text='이 버튼 조합 선택',command=choose).grid(row=6,column=0,columnspan=5,pady=12)
    def choose_trigger(self,chord,gesture):
        if self.busy:return False
        self.swipe_group=None
        matches=[i for i,r in enumerate(self.rows) if r!=EMPTY and editable(r) and int.from_bytes(r[:4],'little')==chord and r[4]==gesture]
        if len(matches)>1:self.toggle_advanced();return False
        index=matches[0] if matches else next((i for i,r in enumerate(self.rows) if r==EMPTY),None)
        if index is None:self.status.set('설정 32개가 모두 사용 중입니다. 설정 목록을 확인하세요.');return False
        self.table.selection_set(str(index));self.select();self.gesture=gesture
        for i,var in enumerate(self.inputs):var.set(bool(chord&(1<<i)))
        if not matches:
            self.output.set('Keyboard');self.keys.set('');self.pending_keyboard=True
            self.action_mode.set('키를 순서대로 한 번 입력' if gesture else '기본 키 지정')
        self.mode_changed();self.output_changed();self.draw_pad();self.update_availability(force=True)
        return True
    def dialog(self,key,title):
        current=self.dialogs.get(key)
        if current is not None and current.winfo_exists():
            current.deiconify();current.lift();current.focus_set();return None
        win=tk.Toplevel(self.frame);win.withdraw();win.title(title);win.transient(self.app.root)
        self.dialogs[key]=win
        def place():
            if not win.winfo_exists():return
            place_popup(win,self.app.root);win.deiconify();win.lift();win.focus_set()
        win.after_idle(place)
        return win
    def swipe_value(self,gesture):
        rows=[r for i,r in enumerate(self.rows) if not self.disabled&(1<<i) and r[4]==gesture and is_swipe(r)]
        if not rows:return '—'
        if len(rows)!=1:return '여러개'
        return OUTPUT_LABELS.get(describe(rows[0])[1],describe(rows[0])[1])
    def draw_swipes(self):
        self.swipe_regions=[];p=self.pad
        if p.winfo_width()<820:return
        existing=set(p.find_all())
        p.create_text(91,108,text='터치패드',fill='#a7b6c9',font=('맑은 고딕',9))
        for row,(direction,arrow) in enumerate(((0,'↑'),(2,'←'),(3,'→'),(1,'↓'))):
            y=139+row*51
            for right in (False,True):
                gesture=0x80|direction|(4 if right else 0)
                selected=self.gesture==gesture;colour='#82e5cc' if selected else '#8293a9'
                # Each half follows the broad top and tapered, rounded lower corners
                # of the DualSense touchpad; the centre seam separates start regions.
                half=[(90,y-17),(55,y-17),(49,y-15),(49,y-10),
                      (54,y+10),(58,y+16),(64,y+17),(90,y+17)]
                if right:half=[(180-x,yy) for x,yy in half]
                p.create_polygon(*[v for point in half for v in point],
                                 fill='#294f53' if selected else '#202c3b',outline=colour,width=2)
                p.create_text(109 if right else 67,y,text=arrow,fill=colour,font=('Segoe UI Symbol',14,'bold'))
                x=153 if right else 23;value=self.swipe_value(gesture)
                p.create_rectangle(x-20,y-14,x+20,y+14,fill='#294f53' if selected else '#202c3b',outline=colour)
                p.create_text(x,y,text=value if len(value)<=4 else value[:3]+'…',fill='#eef4ff' if self.edit_available() else '#7d8795',font=('Segoe UI Symbol',9,'bold'))
                self.swipe_regions.append((gesture,92 if right else 2,y-20,175 if right else 89,y+20))
        factor=min(1,((p.winfo_width()-self.controller_image.width())/2-8)/175)
        for item in set(p.find_all())-existing:p.addtag_withtag('swipes',item)
        p.scale('swipes',0,0,factor,1)
        self.swipe_regions=[(g,x1*factor,y1,x2*factor,y2) for g,x1,y1,x2,y2 in self.swipe_regions]
    def swipe_hit(self,event):
        return next((g for g,x1,y1,x2,y2 in getattr(self,'swipe_regions',[]) if x1<=event.x<=x2 and y1<=event.y<=y2),None)
    def select_swipe(self,gesture):
        if self.choose_trigger(0,gesture):
            self.selection_title.set(('오른쪽' if gesture&4 else '왼쪽')+' 절반 · '+SWIPE_DIRECTIONS[gesture&3]+' 스와이프')
            self.status.set('아래에서 실행할 키를 지정하세요. 한 손가락으로 밀고 떼면 한 번 실행됩니다.')
    def xbox_test_worker(self):
        w=getattr(getattr(self.app,'xbox',None),'worker',None)
        if not self.app.engine and w and w.alive and getattr(w,'phase',None)=='running' and not w.stop_event.is_set() and not w.paused.is_set() and not self.busy and not self.app.closing and not self.app.studio_window.busy:return w
        return None
    def start_keyboard_preview(self):
        self.keyboard_notice=''
        try:self.keyboard_preview.start(int(self.app.root.wm_frame(),0),self.target(),lambda name:self.recent_inputs.append((time.monotonic(),name)))
        except Exception as exc:self.keyboard_notice='Pico 키보드 표시 불가: '+str(exc)
    def toggle_preview(self):
        if self.preview_timer is not None:self.stop_preview();return
        w=self.xbox_test_worker()
        if w is not None:
            self.recent_inputs.clear();self.start_keyboard_preview()
            try:
                self.preview=w.preview;self.preview_mode='xbox';self.preview.start();self.preview_button.configure(text='■ 입력 테스트 종료',background='#b83b3b',foreground='white',activebackground='#d14a4a',activeforeground='white');self.update_preview()
            except Exception as exc:self.stop_preview();self.status.set('입력 테스트 시작 실패: '+str(exc))
            return
        from task_exclusion import source_settings_blocked
        if source_settings_blocked(self.app):
            self.status.set('Xbox를 끈 뒤 장치 설정을 변경하세요. 복구 기록이 남았다면 Xbox 문제 해결에서 먼저 복원하세요.');return
        from task_exclusion import management_busy
        if management_busy(self.app):
            self.status.set('드라이버 관리 작업이 끝난 뒤 입력 테스트를 시작하세요.');return
        try:
            if self.busy or self.app.closing or self.app.studio_window.busy:raise ValueError('현재 작업이 끝난 뒤 테스트하세요.')
            if self.app.engine:raise ValueError('입력 테스트는 오디오햅틱을 정지한 뒤 시작하세요.')
            if getattr(getattr(getattr(self.app,'xbox',None),'worker',None),'alive',False):
                raise ValueError('Xbox 모드를 끈 뒤 입력 테스트를 시작하세요.')
            if getattr(getattr(self.app,'shortcut',None),'thread',None) and self.app.shortcut.thread.is_alive():
                raise ValueError('연결 설정의 PC 음소거 단축키를 끈 뒤 입력 테스트를 시작하세요.')
            self.app.root.focus_set()
            self.recent_inputs.clear();self.keyboard_notice=''
            self.start_keyboard_preview()
            self.preview.start(self.target());self.preview_button.configure(text='■ 입력 테스트 종료',background='#b83b3b',foreground='white',activebackground='#d14a4a',activeforeground='white');self.update_preview()
        except Exception as e:
            self.stop_preview();self.status.set(str(e))
    def update_preview(self):
        self.preview_timer=None
        if self.app.closing or not self.frame.winfo_viewable():self.stop_preview();return
        xbox_test=self.preview_mode=='xbox'
        worker=self.xbox_test_worker() if xbox_test else None
        if xbox_test and (worker is None or self.preview is not worker.preview or not self.preview.enabled):
            if self.stop_preview() is not False:self.status.set('Xbox 입력 테스트 종료')
            return
        while self.preview.events:
            item=self.preview.events.popleft();self.recent_inputs.append(item)
            capture=getattr(self,'pad_combo_capture_event',None)
            if capture is not None:capture(item[1],item[0])
        # Packet and keyboard events have separate producers; keep expiry chronological.
        self.recent_inputs=deque(sorted(self.recent_inputs,key=lambda item:item[0]),maxlen=32)
        self.draw_history()
        mask,status=self.preview.state
        if mask!=self.preview_mask:
            changed=mask^self.preview_mask
            self.preview_mask=mask
            for i,var in enumerate(self.inputs):
                if changed&(1<<i):self.pad.itemconfigure(f'button-{i}',fill='#151b25' if i==16 and self.ps_enabled.get() else '#bb7624' if mask&(1<<i) else '#294f53' if var.get() else '#202c3b')
        received=getattr(self.preview,'last_received',None)
        age='아직 수신 없음' if received is None else f"마지막 {'출력 변경' if xbox_test else '수신'} {max(0.,time.monotonic()-received):.1f}초 전"
        hint=status+' · '+age+' · 최근 입력은 2.5초 후 사라집니다.'+(' · '+(self.keyboard_notice or self.keyboard_preview.error) if self.keyboard_notice or self.keyboard_preview.error else ' · Pico 키보드 입력 포함')
        if self.preview_hint.cget('text')!=hint:self.preview_hint.configure(text=hint)
        if self.preview.thread and not self.preview.thread.is_alive():
            self.stop_preview();self.status.set(status);return
        self.preview_timer=self.app.root.after(50,self.update_preview)
    def stop_preview(self):
        if self.preview_timer is not None:
            self.app.root.after_cancel(self.preview_timer);self.preview_timer=None
        errors=[]
        try:
            if self.keyboard_preview.stop() is False:errors.append(self.keyboard_preview.error)
        except Exception as exc:errors.append(str(exc))
        self.recent_inputs.clear()
        try:
            self.preview.stop()
            if self.device_preview.thread and self.device_preview.thread.is_alive():errors.append('이전 입력 테스트 종료 대기 중 · 잠시 후 다시 시도하세요.')
        except Exception as exc:errors.append(str(exc))
        if self.preview_mode=='xbox':self.preview=self.device_preview
        self.preview_mode='device';self.preview_mask=0
        if hasattr(self,'preview_button') and self.preview_button.winfo_exists():self.preview_button.configure(text='입력 테스트 시작',background='#263445',foreground='white',activebackground='#35475c',activeforeground='white')
        if hasattr(self,'preview_hint') and self.preview_hint.winfo_exists():self.preview_hint.configure(text='패드의 버튼을 클릭하여 아래에서 설정하세요.')
        if hasattr(self,'pad') and self.pad.winfo_exists():self.draw_pad()
        if errors:
            from remap_diagnostics import log
            text='입력 테스트 정리 미완료: '+' · '.join(errors);self.status.set(text);log(text)
        return not errors
    def capture_press(self,event):
        if self.output.get()!='Keyboard' or not self.edit_available() or self.ps_edit_blocked():return 'break'
        self.capture.press(event_key(event))
        if self.capture.invalid:self.status.set('지원하는 키를 최대 4개까지 함께 누르세요.')
        else:self.keys.set('+'.join(self.capture.combo))
        return 'break'
    def capture_release(self,event):
        value=self.capture.release(event_key(event))
        if value:
            self.keys.set(value);self.edit()
        elif not self.capture.down:self.keys.set(keys_text(self.rows[self.index()][7:11]))
        return 'break'
    def capture_blur(self,event=None):
        if self.capture.down:self.keys.set(keys_text(self.rows[self.index()][7:11]))
        self.capture.reset()
    def key_picker(self):
        win=self.dialog('keys','특수키 · 숫자패드')
        if win is None:return
        box=ttk.Frame(win,padding=16);box.pack()
        ttk.Label(box,text='키 이름을 클릭하면 현재 버튼에 지정됩니다.').grid(row=0,column=0,columnspan=4,pady=(0,6))
        modifiers={k:tk.BooleanVar() for k in ('CTRL','SHIFT','ALT','WIN')}
        modrow=ttk.Frame(box);modrow.grid(row=1,column=0,columnspan=4,pady=(0,8))
        for k,var in modifiers.items():ttk.Checkbutton(modrow,text=k,variable=var).pack(side='left')
        names=['BACKSPACE','DELETE','TAB','ENTER','ESC','SPACE','NUMLOCK','NUMENTER','HOME','END','PAGEUP','PAGEDOWN']+[f'F{i}' for i in range(1,13)]+[f'NUM{i}' for i in range(10)]+['NUMDECIMAL','NUMADD','NUMSUBTRACT','NUMMULTIPLY','NUMDIVIDE']
        def choose(name):
            self.capture.reset();self.output.set('Keyboard');self.keys.set('+'.join([k for k,v in modifiers.items() if v.get()]+[name]))
            if self.edit():win.destroy()
        for i,name in enumerate(names):ttk.Button(box,text=name,command=lambda n=name:choose(n)).grid(row=2+i//4,column=i%4,padx=3,pady=3,sticky='ew')
    def chord_changed(self):
        self.draw_pad()
        if self.output.get()!='Keyboard' or self.keys.get():self.edit()
    def reset_all(self):
        try:
            self.local_ready(editing=False)
            if not messagebox.askyesno('모든 버튼 기본값으로','모든 버튼 변경을 끌까요?\n저장한 PC 프리셋 4개는 그대로 남습니다.\nPico 2 W에 적용을 눌러야 실제로 바뀝니다.',parent=self.app.root):return
            # Restore the read table, disable every mapping, and leave shared definitions intact.
            self.rows=list(self.snapshot.rows)
            self.disabled=0xffffffff;self.ps_enabled.set(False)
            self.refresh();self.choose_button(self.selected_button)
            self.status.set('모든 버튼 변경을 껐습니다. Pico 2 W에 적용을 눌러 마무리하세요.')
        except Exception as e:self.status.set(str(e))
    def choose_button(self,button):
        if self.busy:return
        self.gesture=0;self.swipe_group=None;self.action_mode.set('기본 키 지정')
        chord=1<<button
        matches=[i for i,r in enumerate(self.rows) if int.from_bytes(r[:4],'little')==chord and editable(r) and r!=EMPTY]
        from pad_combo import valid_group
        if len(matches)>1 and not valid_group([self.rows[i] for i in matches]):
            self.status.set('같은 버튼에 여러 동작이 있습니다. 전체 목록에서 선택하세요.');self.toggle_advanced();return
        index=matches[0] if matches else next((i for i,r in enumerate(self.rows) if r==EMPTY),None)
        if index is None:self.status.set('매크로 32개가 모두 사용 중입니다. 전체 목록에서 정리하세요.');return
        self.selected_button=button;self.table.selection_set(str(index));self.select()
        if not matches:
            for i,v in enumerate(self.inputs):v.set(i==button)
            self.enabled.set(True);self.hold.set(True);self.replace.set(True)
            self.output.set(BUTTONS[button] if BUTTONS[button] in OUTPUTS else 'Keyboard')
            self.keys.set('');self.label.set('');self.mapping_summary.set('기본 동작')
        self.selection_title.set({'×':'✕','Mute':'음소거','Touchpad':'터치패드'}.get(BUTTONS[button],BUTTONS[button])+' 버튼');self.output_changed();self.mode_changed();self.draw_pad();self.update_availability(force=True)
    def output_changed(self):
        keyboard=self.output.get()=='Keyboard'
        self.key_entry.configure(state='readonly' if keyboard else 'disabled')
        self.key_hint.configure(text='입력칸을 클릭하고 원하는 키를 누르세요 · 조합은 함께 누르기 · 최대 4키' if keyboard else '선택한 게임패드·마우스 동작으로 변경합니다.')
    def help(self):
        messagebox.showinfo('버튼 설정 안내','1. Pico 2 W에서 읽기를 누릅니다.\n2. 패드 그림의 버튼을 고르고 아래에서 실행할 키를 지정합니다.\n3. Pico 2 W에 적용을 누릅니다.\n\n기본 키 지정: 누르는 동안 유지하고 떼면 해제합니다.\n키보드 조합: CTRL+Q처럼 함께 입력할 키를 지정합니다(최대4키).\n키를 순서대로 한 번 입력: 지정한 키를 순서대로 누르고 해제합니다. 시간 간격·반복 편집은 없습니다. 원래 버튼도 전달됩니다.\n터보: 패드 그림에서 원본 버튼을 고르고 아래 터보 옵션을 켜세요. Xbox 호환 모드에서만 작동하며 앱 종료 시 초기화됩니다.\n\n여러 패드 버튼 함께 누르기: L1+✕처럼 입력 조건을 만듭니다.\n터치패드: 왼쪽 그림에서 시작할 절반과 화살표를 고르고 실행할 키를 지정합니다. 한 손가락으로 클릭하지 않고 밀었다 떼세요.\n\n입력 테스트는 PC가 받은 패드 버튼만 주황색으로 표시합니다. Pico에서 숨긴 원래 버튼과 키보드 출력은 보이지 않습니다. 테스트 종료/탭 이동 시 감시를 멈춥니다.\n프리셋을 선택하면 그림에 표시되며, 장치 적용은 별도입니다.\n회색 컨트롤은 현재 편집·적용할 수 없는 상태입니다. 오디오를 정지하고 Pico 2 W에서 다시 읽으세요.',parent=self.app.root)

    def toggle_advanced(self):
        win=self.dialog('settings','저장할 버튼 설정 목록')
        if win is None:return
        self.advanced=win;win.geometry('690x540')
        box=ttk.Frame(win,padding=16);box.pack(fill='both',expand=True)
        ttk.Label(box,text='설정을 선택하고 이 창을 닫으면 아래 편집기에서 바꿀 수 있습니다.').pack(anchor='w')
        style=ttk.Style();style.configure('Remap.Treeview',background='#18212e',fieldbackground='#18212e',foreground='#eef4ff',rowheight=26)
        style.configure('Remap.Treeview.Heading',background='#293546',foreground='#eef4ff')
        style.map('Remap.Treeview',background=[('selected','#294f53')],foreground=[('selected','#b4f4e1')])
        listing=ttk.Treeview(box,style='Remap.Treeview',columns=('on','input','output'),show='headings',height=12,selectmode='browse');self.advanced_list=listing
        for key,title,width in [('on','켜짐',55),('input','입력',375),('output','출력',190)]:listing.heading(key,text=title);listing.column(key,width=width,minwidth=45)
        for i,r in enumerate(self.rows):listing.insert('','end',iid=str(i),values=('✓' if not self.disabled&(1<<i) else '—',*describe(r)))
        listing.pack(fill='both',expand=True,pady=12)
        def selected(event):
            if listing.selection():self.table.selection_set(listing.selection()[0]);self.select()
        listing.bind('<<TreeviewSelect>>',selected)
        ttk.Label(box,text='패드 버튼을 누르는 조건과 그때 실행할 동작을 보여 줍니다. 장치 반영은 [Pico 2 W에 적용]을 누르세요.',wraplength=620).pack(anchor='w')
        ttk.Button(box,text='선택 완료',command=win.destroy).pack(anchor='e',pady=10)
    def refresh_presets(self):
        for i,b in enumerate(self.preset_buttons):
            slot=self.preset_store.slots[i]
            b.configure(text=f'{i+1}  '+(slot['name'] if slot else '빈 프리셋'),style='Selected.TButton' if i==self.preset_index else 'TButton')
    def choose_preset(self,index):
        previous=(self.preset_index,self.preset_name.get())
        self.preset_index=index;slot=self.preset_store.slots[index]
        self.preset_name.set(slot['name'] if slot else f'프리셋 {index+1}');self.refresh_presets()
        if slot:
            if not self.load_preset():
                self.preset_index=previous[0];self.preset_name.set(previous[1]);self.refresh_presets()
        else:self.status.set('빈 저장칸입니다. 현재 편집 내용을 이 프리셋에 저장할 수 있습니다.')
    def save_preset(self):
        try:
            if not self.draft_available():raise ValueError('현재 작업이 끝난 뒤 PC에 저장하세요.')
            if self.pending_keyboard:raise ValueError('미완성 키 입력을 완료하거나 편집을 취소하세요.')
            self.preset_store.save(self.preset_index,self.preset_name.get(),self.rows,self.disabled)
            self.refresh_presets();self.status.set('PC 프리셋 저장 완료 · Pico 2 W 설정은 바뀌지 않았습니다.')
        except Exception as e:self.status.set(str(e))
    def load_preset(self):
        try:
            if self.busy or self.app.closing:raise ValueError('현재 작업이 끝난 뒤 선택하세요.')
            rows,disabled=self.preset_store.load(self.preset_index)
            for i,r in enumerate(rows):
                if self.snapshot and (not editable(r) or not editable(self.snapshot.rows[i])) and r!=self.snapshot.rows[i]:
                    raise ValueError('현재 Pico 2 W의 고급 매크로와 다른 프리셋입니다. 덮어쓰기를 차단했습니다.')
            if has_pending_edits(self) and not messagebox.askyesno('프리셋 불러오기','현재 편집 내용을 선택한 프리셋으로 바꿀까요? Pico 2 W에는 아직 적용하지 않습니다.',parent=self.app.root):return
            self.rows=rows;self.disabled=disabled | (ps_rows(rows) if self.ps_enabled.get() else 0);self.refresh();self.choose_button(self.selected_button)
            self.update_availability();self.status.set('프리셋을 그림에 표시했습니다. Pico 2 W에 적용 전에는 장치 설정이 바뀌지 않습니다.' if self.snapshot else '프리셋 미리보기 · 편집과 적용은 Pico 2 W에서 읽은 뒤 가능합니다.')
            return True
        except Exception as e:self.status.set(str(e))
    def target(self):
        panel=self.app.studio_window;i=panel.device.current()
        if not 0<=i<len(panel.paths):raise ValueError('오디오 탭에서 Studio Pico 2 W을 먼저 조회·선택하세요.')
        return panel.paths[i]
    def draft_available(self):
        return not (self.busy or self.app.closing or self.app.studio_window.busy)
    def edit_available(self):
        try:
            return self.snapshot is not None and not (self.busy or self.app.closing or self.app.studio_window.busy) and self.path==self.target()
        except (ValueError,AttributeError):return False
    def ps_changed(self):
        if self.ps_enabled.get():self.disabled|=ps_rows(self.rows)
        self.refresh();self.update_availability(force=True)
        self.status.set('PS 단축키 설정 변경 · 적용 버튼을 눌러 반영하세요.')
    def ps_edit_blocked(self):
        return self.ps_enabled.get() and (any(v.get() for i,v in enumerate(self.inputs) if i==16) or bool(int.from_bytes(self.rows[self.index()][:4],'little')&(1<<16)))
    def common_changed(self):
        self.update_availability(force=True)
        if self.common_apply.get() and self.snapshot and self.snapshot.profile.get('edited',True):self.status.set('현재 Studio 프로필에 미저장 설정이 있습니다. 먼저 Studio에서 저장하거나, 저장된 프로필을 불러온 뒤 PC 리매핑 프리셋을 선택하세요.')
    def update_availability(self,force=False):
        if not hasattr(self,'apply_button'):return
        observed=getattr(self.app.studio_window,'profile',None)
        previous=getattr(self,'studio_profile_at_read',observed)
        if self.snapshot is not None and not self.busy and observed is not None and previous is not None and (observed.get('index'),observed.get('name'))!=(previous.get('index'),previous.get('name')):
            self.invalidate_snapshot();self.status.set('Studio 프로필이 바뀌었습니다. Pico 2 W에서 다시 읽으세요. 이전 편집은 아직 화면에 보존되어 있습니다.')
        ready=self.edit_available()
        try:target=self.target()
        except ValueError:target=None
        busy=bool(self.busy or self.app.closing or self.app.studio_window.busy)
        preview_ready=self.xbox_test_worker() is not None or ready and not self.app.engine and not getattr(getattr(getattr(self.app,'xbox',None),'worker',None),'alive',False)
        state=(ready,preview_ready,busy,target,self.ps_enabled.get(),self.common_apply.get(),self.pending_keyboard,self.index(),self.output.get(),self.gesture,self.action_mode.get(),editable(self.rows[self.index()]))
        self.turbo_panel.render()
        if not force and state==getattr(self,'availability_state',None):return
        self.availability_state=state
        self.draw_pad()
        def enable_tree(parent,enabled):
            for widget in parent.winfo_children():
                if isinstance(widget,(ttk.Button,ttk.Checkbutton,ttk.Entry,ttk.Combobox)):
                    widget.configure(state=('readonly' if isinstance(widget,(ttk.Entry,ttk.Combobox)) else 'normal') if enabled else 'disabled')
                enable_tree(widget,enabled)
        enable_tree(self.editor,ready and not self.ps_edit_blocked() and editable(self.rows[self.index()]))
        enable_tree(self.bottom,ready)
        self.revert_button.configure(state='normal' if self.draft_available() else 'disabled')
        self.ps_check.configure(state='normal' if ready and not self.pending_keyboard else 'disabled')
        self.common_check.configure(state='normal' if ready else 'disabled')
        self.read_button.configure(state='normal' if target is not None and not busy else 'disabled')
        common_ready=not self.common_apply.get() or self.snapshot and not self.snapshot.profile.get('edited',True) and self.snapshot.profile.get('index') is not None
        self.apply_button.configure(state='normal' if ready and not self.pending_keyboard and common_ready else 'disabled')
        self.temporary_button.configure(state='normal' if ready and not self.pending_keyboard and not self.common_apply.get() else 'disabled')
        for button in (self.restore_temporary_button,self.retry_save_button):
            if button is not None and button.winfo_exists():button.configure(state='normal' if target is not None and not busy else 'disabled')
        self.save_preset_button.configure(state='normal' if self.draft_available() and not self.pending_keyboard else 'disabled')
        self.preview_button.configure(state='normal' if preview_ready else 'disabled')
        if ready and not self.ps_edit_blocked() and editable(self.rows[self.index()]):self.output_changed();self.mode_changed()
        if not preview_ready and self.preview_timer is not None:self.stop_preview()
        if self.preview_timer is None:
            self.preview_hint.configure(text='Xbox 출력 버튼과 Pico 키보드 입력을 확인할 수 있습니다.' if self.xbox_test_worker() is not None else '입력 테스트: 오디오햅틱을 정지하면 시작할 수 있습니다.' if self.app.engine else 'Studio 작업이 끝난 뒤 입력 테스트를 시작하세요.' if busy else 'Pico 2 W에서 읽으면 버튼을 선택하고 설정할 수 있습니다.' if not ready else '패드의 버튼을 클릭하여 아래에서 설정하세요.')
    def refresh(self):
        selected=self.table.selection()
        self.table.delete(*self.table.get_children())
        for i,r in enumerate(self.rows):self.table.insert('', 'end',iid=str(i),values=('✓' if not self.disabled&(1<<i) else '—',*describe(r)))
        self.table.selection_set(selected[0] if selected else '0')
        listing=getattr(self,'advanced_list',None)
        if listing is not None and listing.winfo_exists():
            listing.delete(*listing.get_children())
            for i,r in enumerate(self.rows):listing.insert('','end',iid=str(i),values=('✓' if not self.disabled&(1<<i) else '—',*describe(r)))
    def index(self):
        selected=self.table.selection()
        if not selected:raise ValueError('행을 선택하세요.')
        return int(selected[0])
    def select(self,event=None):
        self.swipe_group=None
        self.pending_keyboard=False
        i=self.index();r=self.rows[i];chord=int.from_bytes(r[:4],'little')
        self.gesture=r[4] if is_swipe(r) else 0
        self.action_mode.set('기본 키 지정' if r!=EMPTY and not r[5]&2 else '키보드 조합' if len([k for k in r[7:11] if k])>1 else '기본 키 지정')
        for j,var in enumerate(self.inputs):var.set(bool(chord&(1<<j)))
        self.enabled.set(not self.disabled&(1<<i));self.hold.set(bool(r[5]&2) if r!=EMPTY else True)
        self.replace.set(bool(r[5]&4) if r!=EMPTY else True)
        self.keys.set(keys_text(r[7:11]));self.label.set(r[19:35].split(b'\0')[0].decode('ascii',errors='replace'))
        self.output.set(OUTPUTS[r[17]] if r[17]<len(OUTPUTS) else 'Keyboard')
        self.selection_title.set(describe(r)[0].replace('×','✕').replace('Mute','음소거')+('' if self.gesture else ' 버튼') if r!=EMPTY else BUTTONS[self.selected_button]+' 버튼')
        output=describe(r)[1]
        self.mapping_summary.set(OUTPUT_LABELS.get(output,output) if r!=EMPTY and not self.disabled&(1<<i) else '기본 동작')
        from pad_combo import tagged,group_indices,valid_group
        group=group_indices(self.rows,chord) if tagged(r) else []
        if group and valid_group([self.rows[j] for j in group]):
            self.action_mode.set('패드 키 조합');self.mapping_summary.set(' + '.join(describe(self.rows[j])[1] for j in group))
        self.output_changed();self.mode_changed();self.draw_pad();self.update_availability(force=True)
    def local_ready(self,editing=True):
        if editing and self.ps_edit_blocked():raise ValueError('PS 리맵을 편집하려면 Studio PS 단축키 사용을 해제하세요.')
        if not editing and self.pending_keyboard:raise ValueError('키보드 입력칸에서 지정할 키를 먼저 누르세요.')
        if self.busy or self.app.closing or self.app.studio_window.busy:raise ValueError('오디오와 Studio 작업을 정지한 뒤 편집하세요.')
        if self.snapshot is None:raise ValueError('먼저 Pico 2 W에서 읽어 주세요.')
        if self.path!=self.target():raise ValueError('선택 Pico 2 W이 바뀌었습니다. 다시 읽으세요.')
        if editing and not editable(self.rows[self.index()]):raise ValueError('기존 고급 매크로는 Studio에서 편집하세요.')
    def edit(self):
        try:
            self.local_ready();i=self.index()
            from pad_combo import tagged,group_indices
            previous=self.rows[i];chord=int.from_bytes(previous[:4],'little')
            if self.action_mode.get()=='패드 키 조합':
                from pad_combo import stage
                targets=[OUTPUTS[self.rows[j][17]] for j in group_indices(self.rows,chord)]
                self.rows,self.disabled=stage(self.rows,self.disabled,chord,targets,not self.replace.get())
                self.refresh();self.select();return True
            if tagged(previous):self.label.set('')
            pulse=self.action_mode.get()=='키를 순서대로 한 번 입력'
            record=(make_swipe(self.gesture&3,bool(self.gesture&4),bool(self.gesture&8),self.output.get(),self.keys.get()) if self.gesture else make_record(sum(1<<j for j,v in enumerate(self.inputs) if v.get()),self.output.get(),self.keys.get(),not pulse,False if pulse else self.replace.get(),self.label.get()))
            group=self.swipe_group
            if tagged(previous):
                for j in group_indices(self.rows,chord):
                    if j!=i:self.rows[j]=EMPTY;self.disabled|=1<<j
            if group is not None:
                self.rows,self.disabled=easy_swipe(self.rows,self.disabled,group,self.output.get(),self.keys.get())
            else:
                self.rows[i]=record
                self.disabled &= ~(1<<i)
            self.enabled.set(True);self.hold.set(True)
            self.refresh();self.select();self.swipe_group=group
            if group is not None:self.selection_title.set('쉬운 스와이프 · '+SWIPE_DIRECTIONS[group])
            self.status.set('설정을 준비했습니다. 임시 적용 또는 Pico에 저장을 누르면 사용할 수 있습니다.')
            return True
        except Exception as e:
            self.pending_keyboard=self.output.get()=='Keyboard'
            self.update_availability(force=True);self.status.set(str(e))
            return False
    def clear(self):
        try:
            self.local_ready();i=self.index()
            from pad_combo import tagged,group_indices
            indices=group_indices(self.rows,int.from_bytes(self.rows[i][:4],'little')) if tagged(self.rows[i]) else [i]
            indices=[j for j,r in enumerate(self.rows) if is_swipe(r) and r[4]&3==self.swipe_group] if self.swipe_group is not None else indices
            if any(not editable(self.rows[j]) for j in indices):raise ValueError('기존 고급 설정은 보존해야 합니다.')
            for j in indices:self.rows[j]=EMPTY;self.disabled|=1<<j
            self.refresh();self.choose_button(self.selected_button)
            self.status.set('선택한 리맵을 지웠습니다. 임시 적용 또는 Pico에 저장을 누르면 반영됩니다.')
        except Exception as e:self.status.set(str(e))
    def revert(self):
        if not self.draft_available():return
        baseline=self.snapshot or self.edit_baseline
        self.rows=list(baseline.rows) if baseline else [EMPTY]*32
        self.disabled=baseline.disabled if baseline else 0xffffffff
        self.ps_enabled.set(bool(baseline.ps_shortcut) if baseline else False);self.pending_keyboard=False;self.refresh();self.choose_button(self.selected_button)
    def invalidate_snapshot(self):
        if self.snapshot is not None:self.edit_baseline=self.snapshot
        self.snapshot=None
    def task(self,fn,pause_audio=False):
        from task_exclusion import source_settings_blocked
        if source_settings_blocked(self.app):
            self.status.set('Xbox를 끈 뒤 장치 설정을 변경하세요. 복구 기록이 남았다면 Xbox 문제 해결에서 먼저 복원하세요.');return
        from task_exclusion import management_busy
        if management_busy(self.app):
            self.status.set('Xbox 시작·종료 또는 드라이버 관리 작업이 끝난 뒤 진행하세요.');return
        if self.busy or self.app.closing:return
        if (self.app.engine and not pause_audio) or self.app.studio_window.busy:
            self.status.set('오디오와 Studio 작업을 정지한 뒤 진행하세요.');return
        if self.stop_preview() is False:return
        self.app.studio_window.cancel_pending()
        if hasattr(self.app,'xbox'):self.app.xbox.pause()
        from remap_diagnostics import log
        log("리맵 작업 시작 · 오디오 일시정지 요청="+str(bool(self.app.engine and pause_audio)))
        self.operation_started=time.monotonic()
        self.busy=True;self.update_availability();self.status.set('읽기/검증 중… 다른 Studio 포털은 닫아 주세요.')
        from xbox_settings_job import bind
        binding=bind(self.app)
        def work():
            try:
                from xbox_settings_job import run
                self.results.put((run(self.app,fn,binding),None))
            except Exception as e:self.results.put((None,str(e)))
        def launch():
            try:threading.Thread(target=work,daemon=True).start()
            except Exception as exc:self.results.put((None,'작업 시작 실패: '+str(exc)))
        self.audio_pause=None
        if self.app.engine and pause_audio:
            try:
                from remap_audio_pause import AudioPause
                self.audio_pause=AudioPause(self)
                self.audio_pause.wait(launch,lambda error:self.results.put((None,error)))
            except Exception as exc:self.results.put((None,'오디오 일시정지 실패: '+str(exc)))
        else:launch()
        self.app.root.after(100,self.poll)
    def poll(self):
        while not self.progress.empty():self.status.set(self.progress.get_nowait())
        try:result,error=self.results.get_nowait()
        except queue.Empty:self.app.root.after(100,self.poll);return
        from remap_diagnostics import log
        elapsed=time.monotonic()-getattr(self,"operation_started",time.monotonic())
        log(f"리맵 작업 전체 · {max(0,elapsed):.3f}초 · "+(error or "완료"))
        self.busy=False
        audio_pause=getattr(self,'audio_pause',None);self.audio_pause=None
        if error:
            self.app.studio_window.invalidate()
            self.invalidate_snapshot();self.update_availability(force=True)
            note='리맵 다시 읽기로 장치 상태를 확인하세요. 편집을 보관하려면 먼저 PC 프리셋에 저장하세요.'
            self.status.set('작업 중단 · '+error+' · '+note)
            from remap_diagnostics import log
            log('리맵 UI 작업 잠금 해제 · 다시 읽기 가능')
            update=getattr(self.app,'update_common_controls',None)
            if callable(update):update()
            return
        applied=result if isinstance(result,Applied) else None
        if applied:result=applied.snapshot
        self.app.studio_window.sync_remap_profile(result.profile)
        self.studio_profile_at_read=dict(result.profile)
        self.snapshot=result;self.edit_baseline=result;self.ps_enabled.set(bool(result.ps_shortcut));self.pending_keyboard=False
        self.rows=list(result.rows);self.disabled=result.disabled;self.refresh();self.choose_button(self.selected_button)
        self.status.set(applied.message if applied else '조회·검증 완료 · 프로필: '+result.profile.get('name','')+' · 버튼을 골라 원하는 동작으로 바꾸세요.')
        self.status.set(self.status.get()+f" · {max(0,elapsed):.1f}초")
        if audio_pause:
            resumed=audio_pause.resume()
            self.status.set(self.status.get()+(' · 오디오햅틱 자동 재개 요청' if resumed else ' · 오디오햅틱은 정지 상태입니다. 연결 상태를 확인하세요.'))
            if getattr(audio_pause,'resume_error',None):self.status.set(self.status.get()+' · '+str(audio_pause.resume_error))
    def read(self):
        try:
            if self.busy or self.app.engine or self.app.studio_window.busy:
                self.status.set('오디오와 Studio 작업을 정지한 뒤 진행하세요.');return
            path=self.target()
            from temporary_remap import path_for,_owners
            if path_for(path).exists() and path not in _owners:
                if messagebox.askyesno('임시 리맵 복구 기록','이전 실행의 임시 리맵 복구 기록이 있습니다. 원래 리맵으로 복원할까요?',parent=self.app.root):
                    self.restore_temporary();return
            if has_pending_edits(self):
                if not messagebox.askyesno('다시 읽기','적용하지 않은 편집을 버리고 다시 읽을까요?',parent=self.app.root):return
            if self.busy:return
            self.path=path
            self.task(lambda:device_operation(path,lambda c:c.read(),lambda:not self.app.closing))
        except Exception as e:self.status.set(str(e))
    def retry_saved_remap(self):
        try:
            path=self.target()
            from temporary_remap import path_for,load,retry_saved
            if not path_for(path).exists() or load(path).get('phase') not in ('saving','committed'):
                self.status.set('재시도할 Pico 저장 기록이 없습니다.');return
            if not messagebox.askyesno('실패한 저장 재시도','현재 화면 편집값 대신, 실패 당시 기록된 리맵을 Pico에 저장할까요?\n다른 설정으로 바뀌었다면 덮어쓰지 않고 중단합니다.',parent=self.app.root):return
            backup=self.app.store.path.parent/'remap_backups'
            def work():
                from remap_connection import ensure_connected
                result=device_operation(path,lambda c:retry_saved(c,path,backup),lambda:not self.app.closing)
                connection=ensure_connected(path,result,lambda:not self.app.closing)
                return Applied(result,'저장 재시도 완료 · '+connection.message)
            self.task(work,pause_audio=True)
        except Exception as exc:self.status.set(str(exc))
    def restore_temporary(self):
        try:
            path=self.target()
            from temporary_remap import path_for,restore_connected
            if not path_for(path).exists():self.status.set('복원할 임시 리맵이 없습니다.');return
            self.task(lambda:restore_connected(path),pause_audio=True)
        except Exception as exc:self.status.set(str(exc))
    def apply(self,temporary=False):
        try:
            self.local_ready(editing=False);snapshot=self.snapshot;rows=tuple(self.rows);mask=self.disabled;path=self.path;ps=self.ps_enabled.get()
            active=[r for i,r in enumerate(rows) if not mask&(1<<i)]
            if self.app.features.value['shortcut']['enabled'] and any(int.from_bytes(r[:4],'little')&(1<<18) for r in active):
                raise ValueError('연결 설정에서 DS5Light 음소거 단축키를 먼저 꺼 주세요.')
            common=self.common_apply.get()
            if common:
                if temporary:raise ValueError('공통 저장은 임시 적용할 수 없습니다.')
                if snapshot.profile.get('edited',True) or snapshot.profile.get('index') is None:raise ValueError('공통 저장 전 현재 Studio 프로필의 미저장 변경을 먼저 저장하고 다시 조회하세요.')
                if not messagebox.askyesno('모든 프로필 공통 저장','저장된 Studio 프로필 전체에 현재 리매핑을 저장할까요?\n다른 설정과 프로필 이름은 보존하고, 작업 후 현재 프로필로 돌아옵니다.\n프로필당 약 1분, 많으면 수십 분 걸릴 수 있습니다. 다른 Studio 포털은 닫아 주세요.\n빈 슬롯·앞으로 추가할 프로필은 포함하지 않습니다.\n실패 시 일부만 저장되거나 현재 프로필이 바뀐 채 남을 수 있습니다.',parent=self.app.root):return
                folder=self.app.store.path.parent/'remap_backups'
                self.task(lambda:apply_common_connected(path,snapshot,rows,mask,False,folder,lambda:not self.app.closing,self.progress.put,ps_enabled=ps),pause_audio=True)
                return
            prompt=('저장하지 않고 임시 적용할까요?\n프로그램 종료 시 원래 리맵으로 복원합니다. 연결이 끊기면 다음 실행에서 리맵 문제 해결 → 임시 적용 전으로 되돌리기가 필요할 수 있습니다.' if temporary else '리맵 정의를 Pico에 저장할까요?\n다른 Studio 프로필에서 사용하는 리맵 정의에도 영향을 줍니다. 활성 상태를 유지하려면 현재 프로필도 저장하세요.')
            if not messagebox.askyesno('임시 적용' if temporary else 'Pico에 저장',prompt,parent=self.app.root):return
            folder=self.app.store.path.parent/'remap_backups'
            live=bool(self.app.engine or getattr(getattr(getattr(self.app,'xbox',None),'worker',None),'alive',False))
            self.task(lambda:apply_connected(path,snapshot,rows,mask,False,folder,lambda:not self.app.closing,ps_enabled=ps,live=live,temporary=temporary),pause_audio=True)
        except Exception as e:self.status.set(str(e))
