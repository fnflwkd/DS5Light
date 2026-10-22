"""On-demand Studio UI. HID work never runs on the audio or Tk thread."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from localization import LANGUAGE
from studio_slots import devices, run_device

def msg(ko,en): return ko if LANGUAGE=='ko' else en

class StudioWindow:
    def __init__(self,app):
        self.app=app; self.busy=False; self.slots=[]; self.paths=[]; self.queue=queue.Queue()
        self.win=tk.Toplevel(app.root); self.win.title(msg('Studio 동글 슬롯','Studio dongle slots'))
        self.win.geometry('700x350'); self.win.minsize(680,350); self.win.protocol('WM_DELETE_WINDOW',self.close)
        box=ttk.Frame(self.win,padding=18); box.pack(fill='both',expand=True)
        ttk.Label(box,text=msg('Studio에 저장된 슬롯 1~10','Slots 1–10 stored on Studio'),font=('Segoe UI',12,'bold')).pack(anchor='w')
        ttk.Label(box,text=msg('PC 게임별 프리셋과 별개입니다. Studio 포털의 슬롯 작업을 먼저 끝내세요.',
            'Separate from PC presets. Finish slot operations in the Studio portal first.'),wraplength=650).pack(anchor='w',pady=10)
        self.device=ttk.Combobox(box,state='readonly'); self.device.pack(fill='x')
        self.device.bind('<<ComboboxSelected>>',self.invalidate)
        row=ttk.Frame(box);row.pack(fill='x',pady=12)
        self.choice=ttk.Combobox(row,state='disabled',width=35);self.choice.pack(side='left',fill='x',expand=True)
        self.refresh=ttk.Button(row,text=msg('조회 / 새로고침','Read / Refresh'),command=self.read);self.refresh.pack(side='left',padx=8)
        self.apply=ttk.Button(row,text=msg('적용','Apply'),command=self.activate,state='disabled');self.apply.pack(side='left')
        self.choice.bind('<<ComboboxSelected>>',self.selection)
        ttk.Label(box,text=msg('적용하면 해당 슬롯의 트리거·자이로 등 전체 설정이 바뀝니다.\n오디오를 정지한 뒤 적용하세요. 슬롯을 저장하거나 덮어쓰지 않습니다.',
            'Apply loads all settings in the slot, including triggers and gyro.\nStop audio before applying. Saved slots are never overwritten.'),wraplength=650).pack(anchor='w')
        self.status=tk.StringVar(value=msg('조회 버튼을 누르세요.','Select Read / Refresh.'))
        ttk.Label(box,textvariable=self.status,wraplength=650).pack(anchor='w',pady=14)
        self.refresh.configure(command=self.discover)
        self.win.after(100,self.poll)
    def close(self):
        if self.busy:
            self.status.set(msg('장치 응답을 기다린 뒤 닫아 주세요.','Wait for the device operation before closing.'));return
        self.win.destroy()
    def invalidate(self,event=None):
        self.slots=[];self.choice.set('');self.choice.configure(values=[],state='disabled');self.apply.configure(state='disabled')
    def selection(self,event=None):
        i=self.choice.current(); enabled=not self.busy and 0<=i<len(self.slots) and self.slots[i].state=='saved'
        self.apply.configure(state='normal' if enabled else 'disabled')
    def task(self,kind,fn):
        if self.busy:return
        self.busy=True;self.refresh.configure(state='disabled');self.apply.configure(state='disabled');self.device.configure(state='disabled');self.choice.configure(state='disabled')
        self.status.set(msg('처리 중…','Working…'))
        def work():
            try:self.queue.put((kind,fn(),None))
            except Exception as exc:self.queue.put((kind,None,str(exc)))
        threading.Thread(target=work,daemon=True).start()
    def discover(self):
        self.invalidate();self.task('devices',devices)
    def read(self):
        i=self.device.current()
        if 0<=i<len(self.paths):self.task('slots',lambda:run_device(self.paths[i]))
    def activate(self):
        if self.app.engine is not None:
            self.status.set(msg('메인 화면에서 오디오를 정지한 뒤 적용하세요.','Stop audio in the main window before applying.'));return
        i=self.choice.current();d=self.device.current()
        if not (0<=i<len(self.slots) and self.slots[i].state=='saved' and 0<=d<len(self.paths)):return
        self.task('activate',lambda:run_device(self.paths[d],i))
    def poll(self):
        if not self.win.winfo_exists():return
        try:kind,result,error=self.queue.get_nowait()
        except queue.Empty:pass
        else:
            self.busy=False;self.refresh.configure(state='normal');self.device.configure(state='readonly')
            if error:
                self.invalidate();self.status.set(msg('실패/결과 미확인: ','Failed / outcome unconfirmed: ')+error)
            elif kind=='devices':
                self.paths=[d['path'] for d in result]
                self.device.configure(values=[f"{i+1}. {d.get('product_string') or 'HID'} · {d.get('serial_number') or '-'}" for i,d in enumerate(result)])
                if self.paths:
                    self.device.current(0);self.status.set(msg('장치를 선택하고 조회하세요.','Select a device and read its slots.'))
                    self.device.bind('<<ComboboxSelected>>',lambda e:(self.invalidate(),self.read()))
                    if len(self.paths)==1:self.read()
                    else:self.device.set('')
                else:self.status.set(msg('연결된 후보 장치가 없습니다.','No candidate device connected.'))
            elif kind=='slots':
                self.slots=result;self.choice.configure(values=[s.label() for s in result],state='readonly');self.choice.current(0);self.selection()
                self.status.set(msg('동글에서 읽었습니다. 목록 선택만으로는 적용되지 않습니다.','Read from dongle. Selecting a row does not apply it.'))
            else:
                self.invalidate()
                text=msg('적용 완료: ','Applied: ')+result['slot'].label()
                if result['deferred']:text+=msg(' · 전원 재연결 후 유지 여부 미확인',' · Persistence deferred')
                if result['reconnect']:text+=msg(' · USB 설정 반영에 동글 재연결 필요. 재연결 후 다시 조회하세요.',' · Reconnect dongle for USB settings, then refresh.')
                self.status.set(text)
        self.win.after(100,self.poll)
