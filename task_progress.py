"""UI-only work indication, driven by the existing app timer; no device polling."""
import time
import re
import tkinter as tk
from tkinter import ttk
from ui_viewport import place_popup

def current_work(app):
    if getattr(app,'closing',False):
        return ('shutdown','프로그램 종료 준비 중',getattr(app,'shutdown_detail','진행 중인 작업을 정리합니다.'),True)
    panel=getattr(app,'studio_window',None)
    if panel is not None and panel.busy:
        settings=getattr(panel,'settings_dialog',None)
        if settings is not None and settings.active:
            title={'save':'현재 프로필 저장 중','apply':'장치 설정 적용 중','read':'장치 설정 읽는 중','diagnostics':'연결 상태 확인 중'}.get(settings.kind,'장치 작업 중')
            return ('studio',title,getattr(settings,'progress_text','작업 준비 중'),settings.kind=='save')
        return ('studio','장치 설정 처리 중',panel.status.get(),getattr(panel,'task_kind','')=='activate')
    remap=getattr(app,'remap_panel',None)
    if remap is not None and remap.busy:return ('remap','버튼 리맵 처리 중',remap.status.get(),True)
    xbox=getattr(app,'xbox',None)
    if xbox is not None:
        if xbox.busy:return ('xbox','Xbox 드라이버·복구 작업 중',getattr(xbox,'latest_progress',xbox.worker.status),False)
        if xbox.worker.alive and xbox.worker.phase in ('starting','stopping'):
            return ('xbox','Xbox 연결·종료 처리 중',getattr(xbox.worker,'progress_text',xbox.worker.status),False)
    engine=getattr(app,'engine',None)
    if engine is not None and (getattr(app,'stopping',False) or getattr(engine,'phase','') in ('starting','reconnecting')):
        return ('audio','오디오 연결·종료 처리 중',engine.status,False)
    if getattr(app,'games_busy',False):return ('games','실행 중인 게임 확인 중','프로그램 목록을 읽고 있습니다.',False)
    return None

def operation_stamp(app,category):
    if category=='shutdown':return getattr(app,'shutdown_started',None),getattr(app,'shutdown_started',None)
    if category=='studio':owner=app.studio_window
    elif category=='remap':owner=app.remap_panel
    elif category=='xbox':owner=app.xbox if app.xbox.busy else app.xbox.worker
    elif category=='audio':return (id(app.engine),getattr(app,'stopping',False)),None
    else:return getattr(app,'games_started',None),getattr(app,'games_started',None)
    stamp=getattr(owner,'operation_started',None)
    return stamp,stamp

class WorkIndicator:
    def __init__(self,app):
        self.app=app;self.window=None;self.key=None;self.started=0
    def update(self):
        work=current_work(self.app)
        if work is None:
            self.close();return
        key,title,detail,writing=work
        token,started=operation_stamp(self.app,key)
        identity=(key,token,title)
        if self.key!=identity:self.started=started if started is not None else time.monotonic();self.key=identity
        if self.window is None or not self.window.winfo_exists():
            win=tk.Toplevel(self.app.root);self.window=win;win.title('작업 진행 중');win.transient(self.app.root)
            box=ttk.Frame(win,padding=18);box.pack(fill='both',expand=True)
            self.heading=ttk.Label(box,font=('맑은 고딕',12,'bold'));self.heading.pack(anchor='w')
            self.detail=ttk.Label(box,wraplength=370);self.detail.pack(anchor='w',pady=(10,8))
            self.bar=ttk.Progressbar(box,mode='indeterminate',length=340);self.bar.pack(fill='x');self.bar.start(80)
            self.elapsed=ttk.Label(box);self.elapsed.pack(anchor='w',pady=(8,0))
            self.note=ttk.Label(box,wraplength=370);self.note.pack(anchor='w',pady=(8,0))
            win.protocol('WM_DELETE_WINDOW',lambda:win.bell())
            place_popup(win,self.app.root)
        seconds=int(time.monotonic()-self.started)
        self.heading.configure(text=title);self.detail.configure(text=detail)
        match=re.match(r'전체 (\d+)% · ',str(detail)) if key=='studio' else None
        mode='determinate' if match else 'indeterminate'
        if str(self.bar.cget('mode'))!=mode:
            self.bar.stop();self.bar.configure(mode=mode)
            if mode=='indeterminate':self.bar.start(80)
        if match:self.bar.configure(value=min(100,int(match.group(1))))
        self.elapsed.configure(text=f'경과 시간 {seconds//60:02d}:{seconds%60:02d} · 완료되면 창이 닫힙니다.')
        note='작업이 겹치지 않도록 관련 버튼을 잠시 잠갔습니다.'
        if writing:note+=' 저장·검증 중에는 USB 연결과 전원을 유지하세요.'
        if key=='shutdown':note='정리가 끝나면 자동으로 닫힙니다. USB 연결과 전원을 유지하세요.'
        if seconds>=30:note+='\n예상보다 오래 걸리고 있습니다. 표시된 단계와 로그를 확인하세요. 진행 막대는 장치 응답을 보장하지 않습니다.'
        self.note.configure(text=note)
    def close(self):
        if self.window is not None and self.window.winfo_exists():
            self.bar.stop();self.window.destroy()
        self.window=None;self.key=None
