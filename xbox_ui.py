"""Optional Xbox mode; all Tk operations remain on the UI thread."""
import queue
import threading
import time
from collections import deque
import tkinter as tk
from tkinter import ttk,messagebox
from xbox_backend import probe,DriverMissing
from xbox_input import XboxInput
from task_exclusion import DRIVER_MUTATIONS,device_work_active
from updater_state import is_off
from xbox_install import install,DriverCancelled,installation_notice
from ui_viewport import place_popup
import hidhide
from driver_state import RebootGate,prune_xbox_logs
import watchdog_service
from pathlib import Path
import os,uuid

class XboxUI:
    def __init__(self,app,parent):
        self.app=app;self.worker=XboxInput();self.jobs=queue.Queue();self.busy=False
        self.driver_reboot=False;self.reboot_gate=RebootGate()
        self.close_retry=False;self.close_error=None;self.close_ack=False
        self.log_path=Path(os.environ['LOCALAPPDATA'])/'DS5Light'/'logs'/('xbox-'+uuid.uuid4().hex+'.log')
        self.worker.report=self.report_progress
        self.start_requested=False;self.cancel=threading.Event();self.dialog=None;self.pending_path=None
        self.logs=deque(maxlen=300);self.log_revision=0;self.rendered_revision=-1;self.operation_started=None
        ttk.Style().configure('Xbox.Accent.TButton',padding=(6,0),font=('맑은 고딕',9))
        self.button=ttk.Button(parent,text='Xbox 360 호환 모드 · OFF',command=self.open,style='Xbox.Accent.TButton')
        self.button.pack(side='right')
    def open(self):
        if self.dialog and self.dialog.winfo_exists():self.dialog.lift();return
        self.dialog=tk.Toplevel(self.app.root);self.dialog.title('Xbox 360 호환 모드')
        box=ttk.Frame(self.dialog,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Xbox 360 호환 모드',font=('맑은 고딕',15,'bold')).pack(anchor='w')
        ttk.Label(box,text='상단에서 선택한 Pico의 입력을 Xbox 패드로 전달합니다.\n오디오햅틱은 기존 시작/정지 버튼으로 함께 사용할 수 있습니다.\nDSX·DS4Windows·Steam Input의 중복 변환은 꺼 주세요.\n게임 일반 진동도 Pico로 전달합니다.\n일반 버튼 리맵은 실행 중 PC에서 처리하고, 종료할 때 원래 장치 설정을 복원합니다.',wraplength=510).pack(anchor='w',pady=10)
        self.label=ttk.Label(box,text=self.worker.status,wraplength=510);self.label.pack(anchor='w',pady=8)
        row=ttk.Frame(box);row.pack(fill='x')
        self.on=ttk.Button(row,text='▶ Xbox 360 호환 모드 켜기',command=self.enable,style='Accent.TButton');self.on.pack(side='left')
        self.off=ttk.Button(row,text='호환 모드 끄기',command=self.disable);self.off.pack(side='left',padx=8)
        self.driver=ttk.Button(row,text='드라이버 확인·설치',command=self.prepare_driver);self.driver.pack(side='left')
        self.remove=ttk.Menubutton(row,text='드라이버 제거 ▾');self.remove.pack(side='left',padx=(8,0))
        remove_menu=tk.Menu(self.remove,tearoff=False)
        remove_menu.add_command(label='가상 Xbox 드라이버(ViGEmBus) 제거',command=self.remove_driver)
        remove_menu.add_command(label='중복 입력 방지 드라이버(HidHide) 제거',command=self.remove_hidhide)
        self.remove.configure(menu=remove_menu)
        ttk.Label(box,text='중복 입력 방지와 숨김 복구는 Xbox 모드에 맞춰 자동으로 처리됩니다.',wraplength=510).pack(anchor='w',pady=(10,0))
        tools=ttk.Frame(box);tools.pack(fill='x',pady=(8,0))
        self.tools_toggle=ttk.Button(tools,text='▸ 보조 도구 · 문제가 있을 때',style='Toolbutton',command=self.toggle_tools)
        self.tools_toggle.pack(anchor='w')
        self.tools_body=ttk.Frame(tools,padding=(12,6,0,0))
        ttk.Label(self.tools_body,text='Xbox 모드가 켜지지 않거나, 끈 뒤 원본 패드가 인식되지 않거나, 앱이 비정상 종료된 뒤 입력이 안 될 때 사용하세요.\n먼저 상태를 확인하고, 설정을 바꿔야 하면 동의를 받습니다.\n특정 게임에서만 입력이 안 되거나 중복되면 다른 변환 앱·Steam Input·게임 설정부터 확인하세요.',wraplength=480).pack(anchor='w')
        hide_row=ttk.Frame(self.tools_body);hide_row.pack(fill='x',pady=(6,0))
        self.trouble=ttk.Button(hide_row,text='Xbox 모드 문제 해결',command=self.troubleshoot);self.trouble.pack(side='left',padx=(0,8))
        ttk.Label(box,text='게임을 종료한 뒤 Xbox 모드를 켜고 게임을 다시 실행하세요.',wraplength=510).pack(anchor='w',pady=(6,0))
        ttk.Label(box,text='드라이버 확인·설치는 Pico 연결 없이 가능합니다.',wraplength=510).pack(anchor='w',pady=(8,0))
        self.progress=ttk.Progressbar(box,mode='indeterminate');self.progress.pack(fill='x',pady=(8,0))
        self.elapsed=ttk.Label(box,text='작업 대기',wraplength=560);self.elapsed.pack(anchor='w')
        self.progress_running=False
        logbox=ttk.Frame(box);logbox.pack(fill='both',expand=True,pady=(6,0))
        self.log_text=tk.Text(logbox,height=7,width=70,wrap='word',state='disabled',font=('맑은 고딕',9))
        scroll=ttk.Scrollbar(logbox,command=self.log_text.yview);scroll.pack(side='right',fill='y')
        self.log_text.configure(yscrollcommand=scroll.set);self.log_text.pack(fill='both',expand=True)
        ttk.Button(box,text='로그 복사',command=self.copy_log).pack(anchor='e')
        self.rendered_revision=-1
        ttk.Label(box,text='문제가 생겼을 때만 보조 도구의 Xbox 모드 문제 해결을 사용하세요.\n필요한 드라이버는 동의 후 자동 설치합니다. 재부팅이 필요할 수 있습니다.',wraplength=510).pack(anchor='w',pady=(12,0))
        self.dialog.transient(self.app.root);place_popup(self.dialog,self.app.root)
        if not self.busy and not self.worker.alive:
            from updater_state import read_state
            self.submit('updater_policy_probe',read_state)
        self.tick()
    def toggle_tools(self):
        if self.tools_body.winfo_manager():
            self.tools_body.pack_forget();self.tools_toggle.configure(text='▸ 보조 도구 · 문제가 있을 때')
        else:
            self.tools_body.pack(fill='x');self.tools_toggle.configure(text='▾ 보조 도구 · 문제가 있을 때')

    def submit(self,kind,fn):
        if self.busy:return
        self.busy=True
        self.operation_started=time.monotonic();self.latest_progress=self.worker.status
        if kind in DRIVER_MUTATIONS and device_work_active(self.app):
            self.jobs.put((kind,None,RuntimeError('배터리·프로필·리맵 작업 완료를 기다리고 오디오·입력 테스트를 정지한 뒤 드라이버 작업을 실행하세요.')));return
        try:
            if kind in DRIVER_MUTATIONS and hasattr(self.app,'shortcut'):self.app.shortcut.stop()
        except Exception as exc:
            self.jobs.put((kind,None,RuntimeError('입력 감시 종료 실패: '+str(exc))));return
        def work():
            try:self.jobs.put((kind,fn(),None))
            except Exception as exc:self.jobs.put((kind,None,exc))
        try:threading.Thread(target=work,daemon=True).start()
        except Exception as exc:self.jobs.put((kind,None,RuntimeError('작업 시작 실패: '+str(exc))))
    def enable(self):
        if self.busy or self.worker.alive or self.app.closing:return
        panel=self.app.studio_window;index=panel.device.current()
        if panel.busy or self.app.remap_panel.busy:
            messagebox.showinfo('Xbox 360','장치 설정 작업이 끝난 뒤 켜 주세요.',parent=self.dialog);return
        self.start_requested=True
        self.pending_path=panel.paths[index] if 0<=index<len(panel.paths) else None;self.worker.status='드라이버 확인 중'
        self.submit('probe',self.probe_vigem)
    def prepare_driver(self):
        if self.busy or self.worker.alive or self.app.closing:return
        self.start_requested=False;self.pending_path=None
        self.worker.status='드라이버 확인 중'
        self.submit('driver_probe',self.probe_vigem)
    def record(self,text):
        if not hasattr(self,'logs'):self.logs=deque(maxlen=300);self.log_revision=0
        line=time.strftime('%H:%M:%S')+'  '+str(text)
        self.logs.append(line);self.log_revision+=1
        path=getattr(self,'log_path',None)
        if path is not None:
            try:
                path.parent.mkdir(parents=True,exist_ok=True)
                rotated=path.exists() and path.stat().st_size>1024*1024
                if rotated:path.replace(path.with_suffix('.previous.log'))
                with path.open('a',encoding='utf8') as f:f.write(line+'\n')
                if rotated or not getattr(self,'logs_pruned',False):
                    prune_xbox_logs(path.parent,path);self.logs_pruned=True
            except OSError:pass
    def copy_log(self):
        self.app.root.clipboard_clear();self.app.root.clipboard_append('\n'.join(self.logs))
    def report_progress(self,text):self.jobs.put(('progress',text,None))
    def remove_driver(self):
        if self.busy or self.worker.alive or self.app.closing:return
        if not messagebox.askyesno('ViGEmBus 드라이버 제거',
            'ViGEmBus 1.22.0 드라이버를 제거할까요?\nDSX·DS4Windows 등 이 드라이버를 사용하는 다른 앱의 가상패드도 사용할 수 없게 됩니다. 해당 앱을 종료해 주세요.\n\n관리자 승인과 재부팅이 필요할 수 있습니다. DS5Light와 기존 오디오햅틱 설정은 삭제하지 않습니다.',
            parent=self.app.root,default=messagebox.NO):return
        self.pending_path=None;self.worker.status='드라이버 제거 중'
        self.record('사용자가 드라이버 제거에 동의했습니다.')
        self.submit('uninstall',lambda:self.install_component(consented=True,cancel=self.cancel,progress=self.report_progress,action='uninstall'))
    def check_hidhide(self,standalone=False):
        self.worker.status='ViGEmBus 확인 완료 · HidHide 확인 중'
        self.submit('hide_driver_probe' if standalone else 'hide_probe',self.probe_hiding)
    def finish_ready(self,standalone):
        if getattr(self,'driver_reboot',False):
            self.worker.status='드라이버 설치 완료 · Windows 재부팅 후 다시 확인하세요.';return
        if standalone:self.worker.status='ViGEmBus + HidHide 준비 완료 · 입력 접근 설정은 Xbox 시작 때 적용합니다.'
        else:self.begin()
    def troubleshoot(self):
        if self.busy or self.worker.alive or self.app.closing:return
        from xbox_troubleshoot_ui import TroubleshootWindow
        window=getattr(self,'trouble_window',None)
        if window is None or not window.window.winfo_exists():self.trouble_window=TroubleshootWindow(self)
        else:window.window.lift()
        self.trouble_window.refresh()
    def set_updater(self,enabled):
        if enabled:raise ValueError('업데이터 자동 실행은 지원하지 않습니다.')
        if self.busy or self.worker.alive or self.app.closing:return
        if not messagebox.askyesno('업데이터 자동 실행 끄기 (권장)','업데이터 자동 실행을 끌까요? (권장)\n끄면 필요할 때 업데이트 확인 버튼으로만 실행합니다.\n\n예: 자동 실행 끄기 · 관리자 승인(UAC) 필요\n아니요: 현재 설정 유지 · Xbox 모드 사용 가능\n\n다른 앱도 사용하는 HidHide 공용 설정입니다.',parent=self.app.root,default=messagebox.NO):return
        self.submit('updater_off',lambda:self.install_component(consented=True,cancel=self.cancel,progress=self.report_progress,action='disable_updater',component='hidhide'))
    def check_updates(self):
        if self.busy or self.worker.alive or self.app.closing:return
        if device_work_active(self.app):
            messagebox.showinfo('업데이트 대기','배터리·프로필·리맵 작업 완료를 기다리고 오디오·입력 테스트를 정지한 뒤 업데이트하세요.',parent=self.app.root);return
        if not messagebox.askyesno('HidHide 업데이트 확인','공식 업데이터를 이번에만 실행합니다. 인터넷으로 업데이트를 확인하고, 설치 여부는 열린 창에서 선택합니다.\n실행 전후 자동 실행 등록을 해제하며 관리자 승인이 필요할 수 있습니다.\n업데이트 창을 닫고 정리가 끝날 때까지 기다려 주세요.\n\n업데이트를 확인할까요?',parent=self.app.root,default=messagebox.NO):return
        self.submit('updater_check',lambda:self.install_component(consented=True,cancel=self.cancel,progress=self.report_progress,action='check_update',component='hidhide'))

    def remove_hidhide(self):
        if self.busy or self.worker.alive or self.app.closing:return
        if not messagebox.askyesno('HidHide 제거',
            'HidHide를 제거할까요? 다른 앱의 원본 패드 숨김도 사용할 수 없게 됩니다.\n설정 프로그램과 게임을 종료하세요. 관리자 승인과 재부팅이 필요할 수 있습니다.',
            parent=self.app.root,default=messagebox.NO):return
        def remove():
            try:self.worker.restore_hiding()
            except (hidhide.CorruptJournal,watchdog_service.CorruptJournal):self.report_progress(self.archive_corrupt())
            except hidhide.Missing:self.report_progress('HidHide 드라이버가 이미 없습니다. 제거 후 남은 기록을 보존합니다.')
            code=self.install_component(consented=True,cancel=self.cancel,progress=self.report_progress,action='uninstall',component='hidhide')
            self.report_progress(watchdog_service.archive())
            hidhide.archive_removed()
            self.worker.use_hidhide=False
            self.worker.clear_restore_errors()
            return code
        self.submit('hide_uninstall',remove)
    def begin(self):
        panel=self.app.studio_window;index=panel.device.current()
        if self.app.closing or panel.busy or self.app.remap_panel.busy or not 0<=index<len(panel.paths) or panel.paths[index]!=self.pending_path:
            self.worker.status='장치 선택이 바뀌었습니다. 다시 켜 주세요.';return
        self.start_requested=False
        self.worker.use_hidhide=True
        if self.app.remap_panel.stop_preview() is False:
            self.start_requested=False;self.record('입력 테스트 정리 후 다시 시도하세요.');return
        self.app.shortcut.stop()
        try:
            self.worker.start(self.pending_path);self.close_on_running=True
        except Exception as exc:self.worker.status='Xbox 작업 시작 실패: '+str(exc)
    def disable(self):
        requested=getattr(self,'start_requested',False)
        self.worker.stop()
        if requested:
            self.start_requested=False;self.worker.status='시작 취소 요청 · 진행 작업 완료를 기다립니다.'
            self.latest_progress=self.worker.status
    def tick(self):
        try:
            while True:
                kind,value,error=self.jobs.get_nowait()
                if kind=='progress':
                    self.latest_progress=str(value);self.record(value);continue
                self.busy=False
                if kind=='close_restore':
                    self.close_error=str(error) if error else None
                    self.record('종료 복구 실패: '+str(error) if error else str(value))
                    continue
                if kind=='close_updater_cleanup':
                    self.shutdown_update_error=str(error) if error else None
                    self.record('종료 전 자동 실행 차단 실패: '+str(error) if error else '종료 전 자동 실행 OFF 확인')
                    continue
                if self.app.closing:
                    if error:
                        from shutdown_cleanup import record_failure
                        self.record('종료 중 관리 작업 실패: '+str(error))
                        self.shutdown_error_saved=record_failure(error)
                        from updater_state import CleanupError
                        if kind=='updater_off' or isinstance(error,CleanupError):self.shutdown_update_error=str(error)
                        elif not isinstance(error,DriverCancelled):self.shutdown_other_error=str(error)
                    continue
                if kind in ('probe','installed_probe','hide_probe','hide_installed_probe','install','hide_install') and not getattr(self,'start_requested',True):
                    self.worker.status='Xbox 시작 취소 완료' if not error else '시작 취소 · 작업 결과: '+str(error)
                    self.record(self.worker.status);continue
                if kind=='trouble_fix' and isinstance(error,hidhide.CorruptJournal):
                    window=getattr(self,'trouble_window',None)
                    if window is not None:window.failed(error)
                    if messagebox.askyesno('손상된 복구 기록',str(error)+'\n\n손상 기록을 별도 파일로 보존할까요? 지금 장치나 서비스 상태는 바꾸지 않습니다. Watchdog 서비스와 기존 기록은 변경하지 않습니다. 기존 장치 숨김 목록은 HidHide 설정에서 확인해야 합니다.',parent=self.app.root,default=messagebox.NO):
                        self.submit('trouble_archive',self.archive_corrupt)
                    else:self.worker.status=str(error)
                    continue
                if kind in ('probe','driver_probe') and isinstance(error,DriverMissing):
                    consent=messagebox.askyesno('Xbox 드라이버 설치',
                        installation_notice('vigem'),parent=self.app.root,default=messagebox.NO)
                    if consent:
                        self.worker.status='포함된 드라이버 검증·설치 중'
                        self.record('사용자가 드라이버 설치에 동의했습니다.')
                        self.submit('driver_install' if kind=='driver_probe' else 'install',lambda:self.install_component(consented=True,cancel=self.cancel,progress=self.report_progress))
                    else:self.worker.status='설치 취소 · Xbox OFF'
                elif kind in ('hide_probe','hide_driver_probe') and isinstance(error,hidhide.Missing):
                    consent=messagebox.askyesno('HidHide 설치·복구',
                        installation_notice('hidhide'),parent=self.app.root,default=messagebox.NO)
                    if consent:
                        self.worker.status='HidHide 설치 중';self.record('사용자가 HidHide 설치에 동의했습니다.')
                        self.submit('hide_driver_install' if kind=='hide_driver_probe' else 'hide_install',
                            lambda:self.install_component(consented=True,cancel=self.cancel,progress=self.report_progress,component='hidhide',action='install'))
                    else:self.worker.status='HidHide 설치 취소 · Xbox OFF'
                elif kind in ('trouble_probe','trouble_fix','trouble_stop','trouble_manual','trouble_archive'):
                    window=getattr(self,'trouble_window',None)
                    if error:
                        self.worker.status='문제 해결 작업 실패: '+str(error)
                        if window is not None:window.failed(error)
                    elif kind=='trouble_archive':
                        self.worker.status=str(value)+' · 기록 보존은 실제 숨김 복구가 아닙니다. HidHide 설정에서 원본 패드 숨김 상태를 확인하세요.'
                        messagebox.showinfo('복구 기록 보존',self.worker.status,parent=self.app.root)
                        if window is not None:window.result(dict(service=None,action=None,text=self.worker.status))
                    elif kind=='trouble_probe':
                        self.record(value['text']);self.worker.status='Xbox 진단 완료'
                        if window is not None:window.result(value)
                    else:
                        from xbox_troubleshoot import diagnose
                        self.submit('trouble_probe',diagnose)
                elif kind=='updater_policy_probe':
                    if error:self.worker.status='업데이터 자동 실행 상태 확인 실패: '+str(error)
                    elif not is_off(value):
                        self.worker.status='업데이터 자동 실행 ON · OFF 권장 (Xbox 모드 사용 가능)'
                        self.set_updater(False)
                    else:self.worker.status='업데이터 자동 실행 OFF · 업데이트 확인 버튼으로만 실행'
                elif kind in ('updater_off','updater_check'):
                    self.worker.status=('업데이트 확인 작업 종료 · 자동 실행 OFF 확인' if kind=='updater_check' else '업데이터 자동 실행 OFF 확인') if not error else '업데이터 작업 실패: '+str(error)
                    if not error and getattr(self,'driver_reboot',False):self.worker.status+=' · Windows 재부팅 필요'
                    window=getattr(self,'trouble_window',None)
                    if window is not None and window.window.winfo_exists():window.updater_status.configure(text=self.worker.status)
                elif kind=='hide_removed_probe':
                    if isinstance(error,hidhide.Missing):self.worker.status='HidHide 제거 완료 · 재부팅이 필요할 수 있습니다.'
                    elif error:self.worker.status='HidHide 제거 후 확인 실패: '+str(error)
                    else:self.worker.status='HidHide가 아직 연결됩니다. 재부팅 후 다시 확인하세요.'
                elif kind=='removed_probe':
                    if isinstance(error,DriverMissing):self.worker.status='제거 완료 · 드라이버 연결 없음'
                    elif error:self.worker.status='제거 후 상태 확인 실패: '+str(error)
                    else:self.worker.status='드라이버가 아직 연결됩니다. 재부팅 후 확인하세요. 다른 버전은 Windows 설치된 앱에서 제거하세요.'
                elif isinstance(error,DriverCancelled):self.worker.status='작업 취소 · '+str(error)
                elif error:self.worker.status='작업 실패 · '+str(error)
                elif kind in ('probe','installed_probe'):
                    self.record('ViGEmBus 연결 확인 완료');self.check_hidhide()
                elif kind in ('driver_probe','driver_installed_probe'):
                    self.check_hidhide(standalone=True)
                elif kind in ('install','driver_install'):
                    if value==3010:
                        self.driver_reboot=True;self.check_hidhide(standalone=kind=='driver_install')
                    else:
                        self.worker.status='드라이버 설치 확인 중'
                        self.submit('driver_installed_probe' if kind=='driver_install' else 'installed_probe',self.probe_vigem)
                elif kind in ('hide_probe','hide_driver_probe','hide_installed_probe','hide_driver_installed_probe'):
                    self.record('HidHide 연결 확인 완료')
                    if value and value.get('inverse'):
                        self.worker.status='HidHide 반전 모드가 켜져 있습니다. 설정 프로그램에서 확인하세요.'
                    else:self.finish_ready('driver' in kind)
                elif kind in ('hide_install','hide_driver_install'):
                    if value==3010:
                        self.driver_reboot=True;self.finish_ready('driver' in kind)
                    else:self.submit('hide_driver_installed_probe' if kind=='hide_driver_install' else 'hide_installed_probe',self.probe_hiding)
                elif kind=='hide_uninstall':
                    if value==3010:self.driver_reboot=True;self.worker.status='HidHide 제거 완료 · 재부팅 필요'
                    else:self.submit('hide_removed_probe',hidhide.probe)
                elif kind=='uninstall':
                    if value==3010:self.driver_reboot=True;self.worker.status='제거 완료 · 재부팅 필요'
                    else:
                        self.worker.status='제거 결과 확인 중';self.submit('removed_probe',probe)
                self.record(self.worker.status)
        except queue.Empty:pass
        window=getattr(self,'trouble_window',None)
        if window is not None:window.render()
        if not self.busy:
            self.operation_started=None
            if not self.worker.alive:self.start_requested=False
        panel=self.app.studio_window;index=panel.device.current()
        failed=not self.worker.alive and (getattr(self.worker,'cleanup_error',None) or getattr(self.worker,'run_error',None))
        failure_key=(id(getattr(self.worker,'stop_event',None)),str(failed)) if failed else None
        if failed and getattr(self,'invalidated_failure',None)!=failure_key:
            self.invalidated_failure=failure_key
            remap=getattr(self.app,'remap_panel',None)
            if remap is not None:
                remap.invalidate_snapshot();remap.update_availability(force=True)
                remap.status.set('Xbox 종료/복구 결과 미확인 · 장치 설정을 다시 읽으세요. '+str(failed))
        elif not failed:self.invalidated_failure=None
        if self.worker.alive:
            if not 0<=index<len(panel.paths) or panel.paths[index]!=self.worker.path:self.disable()
            elif panel.busy or self.app.remap_panel.busy:self.worker.paused.set()
            else:self.worker.paused.clear()
        turbo=getattr(getattr(self.app,'remap_panel',None),'turbo_panel',None)
        if turbo is not None:turbo.render()
        self.button.configure(text='Xbox 360 호환 모드 · '+self.worker.mode_label)
        if getattr(self,'close_on_running',False):
            if self.worker.alive and self.worker.phase=='running' and self.worker.updates>0 and not self.worker.stop_event.is_set():
                self.close_on_running=False
                if self.dialog and self.dialog.winfo_exists():
                    self.progress.stop();self.dialog.destroy();self.dialog=None
            elif not self.worker.alive:self.close_on_running=False
        if self.dialog and self.dialog.winfo_exists():
            if self.worker.cleanup_error and getattr(self,'shown_recovery_error',None)!=self.worker.cleanup_error:
                self.shown_recovery_error=self.worker.cleanup_error
                if not self.tools_body.winfo_manager():self.toggle_tools()
            mode={0:'OFF · 일반 진동',1:'Mix · 게임 진동 + 오디오햅틱',2:'Replace · 오디오햅틱만'}.get(getattr(panel,'ah',None),'미확인 · 장치/설정을 조회하세요')
            self.label.configure(text=self.worker.status+'\nStudio 모드: '+mode)
            self.on.configure(state='disabled' if self.busy or self.worker.alive else 'normal')
            self.off.configure(text='시작 취소' if self.busy and getattr(self,'start_requested',False) else 'Xbox 모드 끄기',state='normal' if self.worker.alive or self.busy and getattr(self,'start_requested',False) else 'disabled')
            self.driver.configure(state='disabled' if self.busy or self.worker.alive else 'normal')
            self.remove.configure(state='disabled' if self.busy or self.worker.alive else 'normal')
            for control in (getattr(self,'trouble',None),):
                if control is None:continue
                control.configure(state='disabled' if self.busy or self.worker.alive else 'normal')
            if self.busy:
                if not getattr(self,'progress_running',False):self.progress.start(30);self.progress_running=True
                elapsed=int(time.monotonic()-(self.operation_started or time.monotonic()))
                self.elapsed.configure(text=f'작업 진행 중 · {elapsed//60:02d}:{elapsed%60:02d} 경과 · 완료까지 기다려 주세요.')
            else:
                self.progress.stop();self.progress_running=False;self.operation_started=None
                self.elapsed.configure(text=self.worker.status)
            if self.rendered_revision!=self.log_revision:
                self.log_text.configure(state='normal');self.log_text.delete('1.0','end')
                self.log_text.insert('end','\n'.join(self.logs));self.log_text.configure(state='disabled');self.log_text.see('end')
                self.rendered_revision=self.log_revision
    @staticmethod
    def probe_hiding():
        result=hidhide.probe()
        return result
    @staticmethod
    def archive_corrupt():
        result=hidhide.archive_corrupt()
        return result+' · 보존한 기록을 확인하고 숨김 수동 복구를 다시 시도하세요.'

    def probe_vigem(self):
        if getattr(self,'driver_reboot',False):raise RuntimeError('Windows 재부팅 후 다시 확인하세요.')
        gate=getattr(self,'reboot_gate',None)
        if gate is not None:gate.ensure()
        return probe()
    def install_component(self,**kwargs):
        gate=getattr(self,'reboot_gate',None)
        if gate is not None and kwargs.get('action')!='disable_updater':gate.current()
        action=kwargs.get('action','install');component=kwargs.get('component','vigem')
        from updater_state import verify
        if component=='hidhide' and action=='disable_updater':
            if kwargs.get('consented') is not True:raise PermissionError('변경 전 사용자 동의가 필요합니다.')
            if kwargs.get('cancel') is not None and kwargs['cancel'].is_set():raise DriverCancelled('작업을 취소했습니다.')
            from updater_state import read_state,is_off
            if is_off(read_state()):
                self.report_progress('업데이터 자동 실행이 이미 OFF입니다. 추가 작업 없이 확인을 마쳤습니다.')
                return 0
        def disable_updates():
            try:
                result=verify(False)
            except Exception:pass
            else:
                self.report_progress(result);return
            install(consented=True,cancel=None,progress=self.report_progress,action='disable_updater',component='hidhide')
            self.report_progress(verify(False))
        guarded=component=='hidhide' and action in ('install','repair','check_update')
        if guarded and kwargs.get('consented') is not True:raise PermissionError('변경 전 사용자 동의가 필요합니다.')
        if guarded and kwargs.get('cancel') is not None and kwargs['cancel'].is_set():raise DriverCancelled('작업을 취소했습니다.')
        if action=='check_update':
            try:disable_updates()
            except Exception as cleanup:
                from updater_state import CleanupError
                raise CleanupError('업데이트 실행 전 자동 실행 차단 미확인: '+str(cleanup)) from cleanup
        error=None;code=None
        try:
            code=install(**kwargs)
            if code in (3010,203):
                self.driver_reboot=True
                if gate is not None:gate.mark()
        except Exception as exc:error=exc
        if guarded:
            try:disable_updates()
            except Exception as cleanup:
                from updater_state import CleanupError
                raise CleanupError(('원래 작업: '+str(error)+' · ' if error else '')+'자동 실행 차단 미확인: '+str(cleanup)) from cleanup
        if error:raise error
        if action=='disable_updater':self.report_progress(verify(False))
        return code
    def finish_close(self):
        if self.worker.alive or self.busy:return False
        update_error=getattr(self,'shutdown_update_error',None)
        if update_error:
            from shutdown_cleanup import record_failure
            saved=record_failure(update_error)
            note='오류 기록을 저장했습니다.' if saved else '오류 기록 저장도 실패했습니다. 화면 내용을 별도로 보관하세요.'
            if messagebox.askretrycancel('종료 전 자동 실행 차단 미확인',update_error+'\n'+note+'\n\n지금 닫으려면 [취소]를 누르세요. 자동 실행 차단이 미확인된 상태로 종료합니다.\n[재시도]는 자동 실행 차단 작업을 다시 실행합니다.',parent=self.app.root,default=messagebox.CANCEL):
                self.submit('close_updater_cleanup',lambda:self.install_component(consented=True,cancel=None,progress=self.report_progress,action='disable_updater',component='hidhide'));return False
            self.shutdown_update_error=None
        other=getattr(self,'shutdown_other_error',None)
        if other:
            note='오류 기록 저장 완료' if getattr(self,'shutdown_error_saved',False) else '오류 기록 저장 실패 · 화면 내용을 보관하세요.'
            messagebox.showwarning('종료 중 작업 실패',other+'\n'+note+'\n해당 작업은 완료되지 않았습니다. 확인 후 종료합니다.',parent=self.app.root)
            self.shutdown_other_error=None
        if not self.worker.use_hidhide and not self.worker.cleanup_error:return True
        if not self.close_retry:
            self.close_retry=True;self.submit('close_restore',self.worker.restore_hiding);return False
        error=self.close_error or self.worker.cleanup_error
        if error and not self.close_ack:
            self.record('종료 전 복구 확인 필요: '+error)
            if messagebox.askretrycancel('Xbox 종료 복구 실패',error+'\n\n재시도: 복구를 다시 시도합니다.\n취소: 복구 기록을 보존하고 종료합니다. 다음 실행에서 Pico 리맵·숨김 복구 상태를 확인하세요.',parent=self.app.root,default=messagebox.CANCEL):
                self.submit('close_restore',self.worker.restore_hiding);return False
            self.close_ack=True
        return True
    def pause(self):self.worker.paused.set()
    def close(self):self.start_requested=False;self.cancel.set();self.worker.stop()
