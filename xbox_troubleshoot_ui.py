"""On-demand troubleshooting window; no background service polling."""
import tkinter as tk
from tkinter import ttk,messagebox
import watchdog_service as watchdog
from xbox_troubleshoot import diagnose
from ui_viewport import place_popup

class TroubleshootWindow:
    def __init__(self,owner):
        self.owner=owner;self.data={};self.service=None
        self.window=tk.Toplevel(owner.app.root);self.window.title('Xbox 모드 문제 해결');self.window.transient(owner.app.root)
        box=ttk.Frame(self.window,padding=16);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Xbox 모드 시작 실패, 종료 뒤 원본 패드 인식 불가,\n비정상 종료 뒤 입력이 안 될 때 사용하세요.',wraplength=510).pack(anchor='w')
        ttk.Label(box,text='문제 해결을 위해 Watchdog를 켰다면 문제가 해결된 뒤 아래 버튼으로 끌 수 있습니다.\n창을 닫거나 Xbox 모드를 꺼도 자동으로 끄지 않습니다.',wraplength=510).pack(anchor='w',pady=(8,8))
        ttk.Label(box,text='진단·복구',font=('맑은 고딕',10,'bold')).pack(anchor='w')
        self.status=ttk.Label(box,text='Watchdog · 확인 중');self.status.pack(anchor='w')
        self.detail=tk.Text(box,height=10,width=65,wrap='word',state='disabled');self.detail.pack(fill='both',expand=True,pady=8)
        row=ttk.Frame(box);row.pack(fill='x')
        self.check=ttk.Button(row,text='상태 다시 확인',command=self.refresh);self.check.pack(side='left')
        self.fix=ttk.Button(row,text='권장 조치 실행',command=self.repair);self.fix.pack(side='left',padx=8)
        ttk.Separator(box).pack(fill='x',pady=8)
        ttk.Label(box,text='선택 관리 · Watchdog (평소에는 변경할 필요 없음)',wraplength=510).pack(anchor='w')
        service_row=ttk.Frame(box);service_row.pack(fill='x',pady=(6,0))
        self.start=ttk.Button(service_row,text='Watchdog 켜기',command=self.start_service);self.start.pack(side='left',padx=(0,8))
        self.stop=ttk.Button(service_row,text='Watchdog 끄기',command=self.stop_service);self.stop.pack(side='left')
        self.manual=ttk.Button(service_row,text='서비스 시작을 수동으로',command=self.manual_service);self.manual.pack(side='left',padx=8)
        ttk.Label(box,text='상태는 창을 열거나 다시 확인할 때, 작업 완료 후 조회합니다.\nWatchdog는 다른 앱도 사용하는 공용 서비스입니다. 끄기는 실행만 중지합니다. 수동 설정은 Windows 시작 시 자동 실행을 막으며, 이미 실행 중인 서비스는 끄지 않습니다. 변경에는 관리자 승인이 필요합니다.',wraplength=510).pack(anchor='w',pady=(8,0))
        ttk.Separator(box).pack(fill='x',pady=10)
        ttk.Label(box,text='HidHide 업데이트 · 자동 실행 없이 필요할 때만 확인',wraplength=510).pack(anchor='w')
        update_row=ttk.Frame(box);update_row.pack(fill='x',pady=(6,0))
        self.update_check=ttk.Button(update_row,text='업데이트 확인',command=self.check_updates);self.update_check.pack(side='left')
        self.updater_off=ttk.Button(update_row,text='업데이터 자동 실행 끄기',command=lambda:self.set_updater(False));self.updater_off.pack(side='left',padx=8)
        self.updater_status=ttk.Label(box,text='설치·업데이트 후 자동 실행 등록을 해제합니다. 평소에는 실행하지 않습니다.',wraplength=510);self.updater_status.pack(anchor='w',pady=(6,0))
        place_popup(self.window,owner.app.root);self.render()
    def check_updates(self):
        if not self.available():return
        self.owner.check_updates()
        if self.owner.busy:self.updater_status.configure(text='업데이트 확인 중 · 공식 창을 닫은 후 자동 실행 차단을 확인합니다.')
        self.render()
    def set_updater(self,enabled):
        if not self.available():return
        self.owner.set_updater(enabled)
        if self.owner.busy:self.updater_status.configure(text='업데이터 자동 실행 설정 중 · 관리자 승인과 완료를 기다립니다.')
        self.render()
    def available(self):
        return not self.owner.busy and not self.owner.worker.alive and not self.owner.app.closing
    def refresh(self):
        if not self.available():return
        self.service=None;self.status.configure(text='Watchdog · 확인 중')
        self.owner.submit('trouble_probe',diagnose);self.render()
    def result(self,data):
        self.data=data;self.service=data.get('service')
        if not self.window.winfo_exists():return
        label={'Running':'ON · 실행 중','Stopped':'OFF · 중지됨'}.get(self.service,'확인 불가 / 전환 중 · 다시 확인하세요')
        mode={'Auto':'자동','Manual':'수동','Disabled':'사용 안 함'}.get(self.data.get('start_mode'),'확인 불가')
        self.status.configure(text='Watchdog · '+label+' / 시작 유형: '+mode)
        self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('end',data['text']);self.detail.configure(state='disabled');self.render()
    def failed(self,error):
        self.service=None;self.data={}
        if self.window.winfo_exists():
            self.status.configure(text='Watchdog · 상태 다시 확인 필요')
            self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('end','작업 실패: '+str(error));self.detail.configure(state='disabled')
        self.render()
    def repair(self):
        if not self.available():return
        action=self.data.get('action')
        if action not in ('restore','watchdog'):return
        prompt='가상 패드·Pico 리맵·숨김 복구를 실행할까요?\nPico 리맵 복구에는 해당 장치가 연결되어 있어야 합니다.' if action=='restore' else '문제 해결을 위해 Watchdog를 켤까요? 관리자 승인이 필요합니다. 문제가 해결되면 이 창에서 끌 수 있습니다.'
        if not messagebox.askyesno('문제 해결 조치',prompt,parent=self.window,default=messagebox.NO):return
        fn=self.owner.worker.restore_hiding if action=='restore' else lambda:watchdog.ensure_running(self.owner.report_progress)
        self.owner.submit('trouble_fix',fn);self.render()
    def start_service(self):
        if not self.available() or self.service!='Stopped':return
        if not messagebox.askyesno('Watchdog 켜기','문제 해결을 위해 Watchdog를 켤까요? 관리자 승인이 필요합니다.\n다른 앱도 사용하는 공용 서비스입니다. Xbox 모드나 DS5Light를 종료해도 계속 실행됩니다.\n문제가 해결되면 이 창의 Watchdog 끄기로 중지할 수 있습니다.',parent=self.window,default=messagebox.NO):return
        self.owner.submit('trouble_fix',lambda:watchdog.ensure_running(self.owner.report_progress));self.render()
    def stop_service(self):
        if not self.available() or self.service!='Running':return
        if not messagebox.askyesno('Watchdog 끄기','문제가 해결되었다면 Watchdog를 끌 수 있습니다.\n다른 앱도 사용하는 공용 보호 서비스가 중지됩니다. 관리자 승인이 필요합니다.\n\nWatchdog를 끌까요?',parent=self.window,default=messagebox.NO):return
        self.owner.submit('trouble_stop',lambda:watchdog.ensure_stopped(self.owner.report_progress));self.render()
    def manual_service(self):
        if not self.available() or self.data.get('start_mode')!='Auto':return
        if not messagebox.askyesno('Watchdog 시작 유형 변경','Watchdog 서비스 시작 유형을 자동에서 수동으로 바꿀까요?\nWindows 시작 시 자동 실행되지 않도록 설정합니다. 이미 실행 중이면 별도로 Watchdog 끄기를 눌러야 합니다.\n다른 앱도 사용하는 공용 설정이며 관리자 승인이 필요합니다.',parent=self.window,default=messagebox.NO):return
        self.owner.submit('trouble_manual',lambda:watchdog.ensure_manual(self.owner.report_progress));self.render()
    def render(self):
        if not self.window.winfo_exists():return
        ready=self.available()
        self.manual.configure(state='normal' if ready and self.data.get('start_mode')=='Auto' else 'disabled')
        for button in (self.update_check,self.updater_off):button.configure(state='normal' if ready else 'disabled')
        self.check.configure(state='normal' if ready else 'disabled')
        self.fix.configure(state='normal' if ready and self.data.get('action') else 'disabled')
        self.start.configure(state='normal' if ready and self.service=='Stopped' else 'disabled')
        self.stop.configure(state='normal' if ready and self.service=='Running' else 'disabled')
        if self.owner.busy:self.status.configure(text='Watchdog · 작업 중 (완료 후 상태 확인)')
        else:
            label={'Running':'ON · 실행 중','Stopped':'OFF · 중지됨'}.get(self.service,'확인 불가 / 전환 중 · 다시 확인하세요')
            mode={'Auto':'자동','Manual':'수동','Disabled':'사용 안 함'}.get(self.data.get('start_mode'),'확인 불가')
            self.status.configure(text='Watchdog · '+label+' / 시작 유형: '+mode)
