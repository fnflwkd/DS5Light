"""On-demand device settings/diagnostics. No idle polling or device writes."""
import json
import os
import queue
import sys
import tkinter as tk
from tkinter import ttk,messagebox
from pathlib import Path
from datetime import datetime,timezone
from remapping import device_operation
from device_settings import read_options,set_option,save_current,encode_settings
from ui_help import help_icon
from remap_state import has_pending_edits

class DeviceSettingsWindow:
    def __init__(self,panel,parent=None):
        self.panel=panel;self.app=panel.app;self.data=None;self.active=False;self.events=queue.Queue();self.timer=None;self.pending_edits={}
        self.embedded=parent is not None
        if self.embedded:
            self.win=ttk.Frame(parent);self.win.pack(fill='x')
        else:
            self.win=tk.Toplevel(self.app.root);self.win.title('장치 설정 · 진단');self.win.transient(self.app.root)
        box=ttk.Frame(self.win,padding=0 if self.embedded else 16);box.pack(fill='both',expand=True)
        heading=ttk.Frame(box);heading.pack(fill='x',pady=(0,5))
        ttk.Label(heading,text='듀얼센스').pack(side='left')
        help_icon(heading,'각 임시 적용 버튼은 해당 항목을 장치에 반영하고 재조회합니다. 저장 슬롯에는 기록하지 않습니다.\n현재 프로필에 저장을 누르면 화면 값을 적용하고 저장합니다. 임시 적용은 저장 없이 시험할 때 사용하세요. 앱 종료 시 자동으로 되돌리는 기능은 아닙니다.')
        self.caption=ttk.Label(box,text='설정을 읽은 후 변경할 수 있습니다.',wraplength=400 if self.embedded else 570);self.caption.pack(anchor='w')
        self.widgets=[]
        row=ttk.Frame(box);row.pack(fill='x',pady=3)
        ttk.Label(row,text='폴링레이트').pack(side='left')
        help_icon(row,'PC USB 보고 주기입니다. 실시간은 고정 Hz가 아닙니다.\n변경 후 USB 재연결이 필요할 수 있으므로 먼저 현재 프로필에 저장하세요.')
        self.rate=ttk.Combobox(row,values=['250 Hz','500 Hz','실시간'],width=15,state='disabled');self.rate.pack(side='left',padx=8)
        b=ttk.Button(row,text='임시 적용',command=lambda:self.apply('polling',self.rate.current()),state='disabled');b.pack(side='right');self.widgets.extend([self.rate,b])
        row=ttk.Frame(box);row.pack(fill='x',pady=3)
        ttk.Label(row,text='사용하지 않을 때 연결 끊기 (분)').pack(side='left')
        help_icon(row,'듀얼센스 입력이 없을 때 연결을 해제하는 대기 시간입니다. 5~60분으로 설정합니다.')
        self.minutes=tk.StringVar(value='');self.idle_value=tk.DoubleVar(value=5)
        self.spin=ttk.Scale(row,from_=5,to=60,variable=self.idle_value,command=self.idle_changed,state='disabled');self.spin.pack(side='left',fill='x',expand=True,padx=8)
        ttk.Label(row,textvariable=self.minutes,width=3,anchor='e').pack(side='left')
        b=ttk.Button(row,text='임시 적용',command=self.apply_idle,state='disabled');b.pack(side='right');self.widgets.extend([self.spin,b])
        row=ttk.Frame(box);row.pack(fill='x',pady=3)
        self.never=tk.BooleanVar(value=False)
        self.check=ttk.Checkbutton(row,text='자동 연결 해제 안 함',variable=self.never,state='disabled');self.check.pack(side='left')
        help_icon(row,'체크한 뒤 임시 적용하면 입력이 없어도 자동으로 연결을 해제하지 않습니다.')
        b=ttk.Button(row,text='임시 적용',command=lambda:self.apply('never_disconnect',int(self.never.get())),state='disabled');b.pack(side='right');self.widgets.extend([self.check,b])
        row=ttk.Frame(box);row.pack(fill='x',pady=(6,3))
        ttk.Label(row,text='설정',width=6).pack(side='left')
        self.read_button=ttk.Button(row,text='설정 다시 읽기',command=self.read);self.read_button.pack(side='left')
        self.save_button=ttk.Button(row,text='현재 프로필에 저장',command=self.save,state='disabled');self.save_button.pack(side='left',padx=8)
        help_icon(row,'화면의 설정을 적용한 뒤 현재 슬롯에 저장합니다. 이름을 유지하고 기존 슬롯을 PC에 백업한 뒤 재조회합니다.\n오디오를 정지하고, 미적용 버튼 편집은 먼저 적용하거나 취소하세요.')
        logs=ttk.Frame(box);self.logs_frame=logs
        if not self.embedded:logs.pack(fill='both',expand=True,pady=10)
        self.text=tk.Text(logs,width=1 if self.embedded else 76,height=4 if self.embedded else 14,wrap='word',state='disabled');self.text.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(logs,command=self.text.yview);scroll.pack(side='right',fill='y');self.text.configure(yscrollcommand=scroll.set)
        tools=ttk.Frame(box);tools.pack(fill='x',pady=3);self.tools=tools
        ttk.Label(tools,text='진단',width=6).pack(side='left')
        self.diag_button=ttk.Button(tools,text='연결 상태 확인',command=self.diagnose);self.diag_button.pack(side='left',padx=(0,8))
        if self.embedded:ttk.Button(tools,text='로그 보기 / 접기',command=self.toggle_logs).pack(side='left')
        ttk.Button(tools,text='로그 복사',command=self.copy).pack(side='left',padx=8)
        if not self.embedded:self.win.protocol('WM_DELETE_WINDOW',self.close)
        self.win.bind('<Destroy>',self.destroyed,add='+')
    def destroyed(self,event):
        if event.widget is self.win and self.timer:self.win.after_cancel(self.timer);self.timer=None
    def toggle_logs(self):
        if self.logs_frame.winfo_manager():self.logs_frame.pack_forget()
        else:self.logs_frame.pack(fill='both',expand=True,pady=4,before=self.tools)
    def log(self,text):
        if not self.win.winfo_exists():return
        if self.active:
            self.progress_text=str(text);self.caption.configure(text=self.progress_text)
        self.text.configure(state='normal');self.text.insert('end',str(text)[:16000]+'\n')
        # Retain recent diagnostics only, even if this panel stays open for days.
        excess=int(self.text.index('end-1c').split('.')[0])-400
        if excess>0:self.text.delete('1.0',f'{excess+1}.0')
        self.text.configure(state='disabled');self.text.see('end')
    def copy(self):self.win.clipboard_clear();self.win.clipboard_append(self.text.get('1.0','end-1c'))
    def close(self):
        if self.active:self.log('진행 중인 작업이 끝난 뒤 창을 닫아 주세요.');return
        self.win.destroy()
    def selected(self):
        p=self.panel;i=p.device.current()
        return p.paths[i] if 0<=i<len(p.paths) else None
    def invalidate(self):
        self.data=None;self.pending_edits={}
        self.rate.set('');self.minutes.set('');self.never.set(False)
        self.caption.configure(text='설정을 읽은 후 변경할 수 있습니다.');self.render()
    def update_profile(self,profile):
        if self.data is None:return
        previous=self.data['profile']
        if profile is None or (previous['index'],previous['name'])!=(profile['index'],profile['name']):
            self.invalidate()
        else:self.data['profile']=dict(profile)
    def ready(self,write=False):
        if getattr(self.app,'closing',False) or self.active or self.panel.busy or getattr(getattr(self.app,'remap_panel',None),'busy',False):return False
        if write and self.app.engine is not None:self.log('오디오를 정지한 뒤 적용·저장하세요.');return False
        return True
    def launch(self,fn,kind):
        if not self.ready():return
        if kind!='apply':self.pending_edits={}
        self.progress_text='작업 준비 중 · 장치 응답을 기다립니다.'
        self.active=True;self.kind=kind;self.caption.configure(text='작업 중…');self.render()
        self.panel.extension_done=self.done
        self.panel.task('extension',fn,readonly=kind in ('read','diagnostics'))
        if not self.panel.busy:self.active=False;self.render();return
        self.drain()
    def drain(self):
        self.timer=None
        while not self.events.empty():self.log(self.events.get_nowait())
        if self.active:self.timer=self.win.after(200,self.drain)
    def run(self,path,fn):
        token=self.panel.cancelled
        return device_operation(path,fn,lambda:not token.is_set() and not self.app.closing)
    def read(self):
        if not self.ready():return
        path=self.selected()
        if path is None:self.log('먼저 상단에서 장치를 조회·선택하세요.');return
        self.launch(lambda:self.run(path,read_options),'read')
    def idle_changed(self,value):
        self.minutes.set(str(max(5,min(60,round(float(value))))))
    def apply_idle(self):
        try:value=int(self.minutes.get())
        except ValueError:self.log('대기 시간은 5~60 사이의 정수로 입력하세요.');return
        self.apply('idle_minutes',value)
    def edits(self):
        if not self.data:return {}
        try:minutes=int(self.minutes.get())
        except ValueError:minutes=None
        current=dict(polling=self.rate.current(),idle_minutes=minutes,never_disconnect=int(self.never.get()))
        return {key:current[key] for key,value in self.data['values'].items() if key in current and current[key]!=value}
    def apply(self,key,value):
        if not self.ready(True) or not self.data:return
        path=self.selected()
        if path!=self.data['path']:self.log('선택 장치가 바뀌었습니다. 다시 조회하세요.');return
        expected=dict(self.data['profile'])
        self.pending_edits={k:v for k,v in self.edits().items() if k!=key}
        self.launch(lambda:self.run(path,lambda c:set_option(c,expected,key,value)),'apply')
    def save(self):
        if not self.ready(True) or not self.data:return
        path=self.selected();expected=dict(self.panel.profile or self.data['profile'])
        if path!=self.data['path'] or expected['index'] is None:self.log('현재 슬롯을 다시 조회하세요.');return
        changes=dict(self.data['values']);changes.update(self.edits())
        panel=self.panel
        if panel.intensity_known:changes['intensity']=round(panel.intensity_value.get())
        for key in ('gain','trigger'):
            if panel.extra[key]['known']:
                value=panel.extra[key]['value'].get();changes[key]=round(value,2) if key=='gain' else round(value)
        try:encode_settings(changes)
        except ValueError as exc:self.log(str(exc));return
        remap=getattr(self.app,'remap_panel',None)
        if remap and has_pending_edits(remap):
            self.log('아직 적용하지 않은 버튼 편집이 있습니다. 먼저 적용하거나 편집을 취소하세요.');return
        self.panel.cancel_edit()
        if not messagebox.askyesno('현재 프로필 저장',f"{expected['index']+1:02d} · {expected['name']} 슬롯에 화면의 현재 설정을 적용하고 저장할까요?\n기존 슬롯을 PC에 백업하고 저장 내용을 재조회합니다.\n저장 중에는 전원과 USB 연결을 유지하고 다른 Studio 포털을 닫아 주세요.",parent=self.win,default=messagebox.NO):return
        folder=Path(os.environ.get('LOCALAPPDATA',str(Path.cwd()/'work')))/'DS5Light'/'profile-backups'
        self.launch(lambda:self.run(path,lambda c:save_current(c,expected,folder,self.events.put,changes=changes,path=path)),'save')
    def diagnose(self):
        if not self.ready():return
        path=self.selected()
        report=dict(time=datetime.now(timezone.utc).isoformat(),python=sys.version,platform=sys.platform,
                    selected_hid=repr(path),cached_audio_devices=getattr(self.app,'ds',[]),
                    audio=self.app.engine.stats() if self.app.engine else getattr(self.app,'last_engine_stats',None),
                    studio_status=self.panel.status.get(),profile=self.panel.profile,
                    note='읽기 전용 · PC 처리/큐 통계는 무선 손실·실제 진동 지연 측정이 아닙니다.')
        def collect():
            if path:
                try:report['device']=self.run(path,read_options)
                except Exception as exc:report['device_error']=str(exc)
            else:report['device_error']='선택한 Pico 없음'
            try:
                from xbox_backend import probe
                probe();report['vigem']='연결 가능'
            except Exception as exc:report['vigem']=str(exc)
            from hidhide import diagnostics
            report['hidhide']=diagnostics()
            xbox=getattr(self.app,'xbox',None)
            if xbox is not None:report['xbox_log']=str(getattr(xbox,'log_path',''))
            return report
        self.launch(collect,'diagnostics')
    def done(self,result,error):
        pending=self.pending_edits;self.pending_edits={}
        self.active=False
        if self.timer:self.win.after_cancel(self.timer);self.timer=None
        self.drain()
        if error:self.data=None;self.log('실패 / 결과 미확인: '+error);self.caption.configure(text='실패 · 다시 조회하세요.')
        elif self.kind=='diagnostics':
            self.log(json.dumps(result,ensure_ascii=False,indent=2,default=str));self.caption.configure(text='읽기 전용 진단 완료')
            if self.embedded and not self.logs_frame.winfo_manager():self.toggle_logs()
        elif self.kind=='save':
            for key,value in result.get('settings',{}).items():
                if key in ('polling','idle_minutes','never_disconnect'):self.data['values'][key]=value
                else:self.panel.confirmed[key]=value
            self.data['profile']=result['profile'];self.panel.show_profile(result['profile'])
            self.log(result['message']);self.log('백업: '+result['backup']);self.caption.configure(text='저장·재조회 완료 · 상세 내용은 로그에서 확인하세요.')
        else:
            self.panel.show_profile(result['profile']);self.data=dict(result,path=self.selected())
            values=result['values'];self.rate.current(values['polling']) if 'polling' in values else self.rate.set('')
            self.idle_value.set(values.get('idle_minutes',5));self.minutes.set(str(values.get('idle_minutes','')));self.never.set(bool(values.get('never_disconnect',0)))
            self.caption.configure(text=f"현재 프로필: {result['profile']['name'] or '이름 미확인'} · Studio {result['firmware']}")
            self.log('현재 설정 '+json.dumps(values,ensure_ascii=False))
            if result['errors']:self.log('조회 실패: '+str(result['errors']))
            if self.kind=='apply':
                for key,value in pending.items():
                    if key not in values:continue
                    if key=='polling':self.rate.current(value)
                    elif key=='idle_minutes':
                        if value is not None:self.idle_value.set(value)
                        self.minutes.set('' if value is None else str(value))
                    elif key=='never_disconnect':self.never.set(bool(value))
                self.log('현재 장치에 적용·재조회 완료 · 지속하려면 현재 프로필에 저장하세요.')
                if self.edits():self.caption.configure(text='다른 항목의 편집값은 유지했습니다. 각 항목을 임시 적용하세요.')
        self.render()
    def render(self):
        values=self.data['values'] if self.data else {}
        for i,key in enumerate(('polling','idle_minutes','never_disconnect')):
            enabled=not self.active and key in values
            for j,w in enumerate(self.widgets[2*i:2*i+2]):w.configure(state=('readonly' if i==0 and j==0 else 'normal') if enabled else 'disabled')
        self.save_button.configure(state='normal' if not self.active and self.data and self.data['profile']['index'] is not None else 'disabled')
        for w in (self.read_button,self.diag_button):w.configure(state='disabled' if self.active else 'normal')

