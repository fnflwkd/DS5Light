"""On-demand Studio UI. HID work never runs on the audio or Tk thread."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from localization import LANGUAGE
from studio_slots import devices, run_device

def msg(ko,en): return ko if LANGUAGE=='ko' else en

class StudioWindow:
    def __init__(self,app,parent=None,auto_read=True):
        self.app=app; self.busy=False; self.slots=[]; self.paths=[]; self.queue=queue.Queue(); self.connected=False; self.intensity_known=False; self.generation=0; self.poll_id=None; self.edit_id=None; self.startup_id=None; self.confirmed={}
        self.embedded=parent is not None
        if self.embedded:
            self.win=ttk.Frame(parent);self.win.pack(fill='both',expand=True)
        else:
            self.win=tk.Toplevel(app.root);self.win.title(msg('Studio 설정','Studio settings'))
            self.win.geometry('520x720');self.win.minsize(500,720);self.win.protocol('WM_DELETE_WINDOW',self.close)
        box=ttk.Frame(self.win,padding=0 if self.embedded else 18);box.pack(fill='both',expand=True)
        self.wrapped=[]
        def note(text,pady=(5,0)):
            label=ttk.Label(box,text=text,wraplength=440,style='Muted.TLabel');label.pack(anchor='w',fill='x',pady=pady);self.wrapped.append(label);return label
        ttk.Label(box,text=msg('03   Studio 동글 설정','03   Studio dongle settings'),font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,10))
        dr=ttk.Frame(box);dr.pack(fill='x')
        self.device=ttk.Combobox(dr,state='readonly',width=18);self.device.pack(side='left',fill='x',expand=True)
        self.device.bind('<<ComboboxSelected>>',self.invalidate)
        self.refresh=ttk.Button(dr,text=msg('조회','Refresh'),command=self.discover);self.refresh.pack(side='left',padx=(6,0))
        self.loaded_label=note(msg('현재 슬롯 · 미확인','Current slot · unconfirmed'),(10,6))
        row=ttk.Frame(box);row.pack(fill='x')
        self.choice=ttk.Combobox(row,state='disabled',width=22);self.choice.pack(side='left',fill='x',expand=True)
        self.apply=ttk.Button(row,text=msg('적용','Apply'),command=self.activate,state='disabled');self.apply.pack(side='left',padx=(6,0))
        self.choice.bind('<<ComboboxSelected>>',self.selection)
        note(msg('오디오 정지 후 슬롯 적용 · 트리거·자이로 등 전체 설정이 바뀝니다. 저장된 슬롯은 덮어쓰지 않습니다.',
                 'Stop audio to apply a slot, including triggers and gyro. Saved slots are not overwritten.'))
        self.extra={};self.strength_order=[]
        for key,title,description,lo,hi in (
            ('gain',msg('햅틱 전체 강도 (Gain) 조절','Overall haptics strength (Gain)'),msg('100~200% · 네이티브·오디오햅틱 모두에 영향','100–200% · affects native and audio-derived haptics'),1,2),
            ('intensity',msg('오디오햅틱 강도','Audio-haptics strength'),msg('Studio Intensity · PC 억제 강도와 별개','Studio Intensity · separate from PC suppression'),0,200),
            ('trigger',msg('적응형 트리거 강도 감소','Adaptive-trigger strength reduction'),msg('좌우 공통 · 10은 최대 감소 요청. 효과에 따라 적용되지 않을 수 있습니다.','Both sides · 10 requests maximum reduction. Some effects may not respond.'),0,10)):
            self.strength_order.append(key)
            ttk.Label(box,text=title).pack(anchor='w',pady=(18,5))
            row=ttk.Frame(box);row.pack(fill='x');value=tk.DoubleVar(value=100 if key=='intensity' else lo)
            scale=ttk.Scale(row,from_=lo,to=hi,variable=value,state='disabled');scale.pack(side='left',fill='x',expand=True)
            number=ttk.Label(row,text='—',width=7,anchor='e');number.pack(side='left',padx=(8,0))
            if key=='intensity':
                self.intensity_value=value;self.intensity_scale=scale;self.intensity_number=number
                value.trace_add('write',lambda *args:self.intensity_number.configure(text=f'{round(self.intensity_value.get())}%'))
                self.intensity_read=ttk.Button(row,command=self.read_intensity,state='disabled')
                self.intensity_apply=ttk.Button(row,command=self.apply_intensity,state='disabled')
            else:
                value.trace_add('write',lambda *a,k=key:self.extra_number(k))
                read=ttk.Button(row,command=lambda k=key:self.extra_task(k,False),state='disabled')
                apply=ttk.Button(row,command=lambda k=key:self.extra_task(k,True),state='disabled')
                self.extra[key]=dict(value=value,scale=scale,number=number,read=read,apply=apply,known=False)
            self.bind_strength(scale,key);note(description)
        note(msg('손을 놓으면 현재 동글 설정에 적용됩니다. 조작하지 않을 때는 강도를 조회하지 않습니다.','Release to apply current dongle settings. No strength polling while idle.'),(18,0))
        note(msg('DS5 Light 프리셋에는 Studio 값이 저장되지 않습니다.','DS5 Light presets do not save Studio values.'))
        self.status=tk.StringVar(value=msg('조회 버튼을 누르세요.','Select Refresh.'))
        self.status_label=note('');self.status_label.configure(textvariable=self.status)
        box.bind('<Configure>',lambda event:[w.configure(wraplength=max(200,event.width-4)) for w in self.wrapped])
        if auto_read:self.startup_id=self.win.after(100,self.initial_read)
    def initial_read(self):
        self.startup_id=None;self.discover()
    def bind_strength(self,widget,key):
        widget.bind('<ButtonRelease-1>',lambda e:self.schedule_strength(key,40))
        widget.bind('<KeyRelease>',lambda e:self.schedule_strength(key,300))
    def cancel_edit(self):
        if self.edit_id:self.win.after_cancel(self.edit_id);self.edit_id=None
    def schedule_strength(self,key,delay=40):
        if self.busy:return
        self.cancel_edit();self.edit_id=self.win.after(delay,lambda:self.commit_strength(key))
    def commit_strength(self,key):
        self.edit_id=None
        if self.busy or not self.connected:return
        value=round(self.intensity_value.get()) if key=='intensity' else round(self.extra[key]['value'].get(),2) if key=='gain' else round(self.extra[key]['value'].get())
        if value==self.confirmed.get(key):return
        if key=='intensity':self.apply_intensity()
        else:self.extra_task(key,True)
    def read_strengths(self):
        d=self.device.current()
        if not 0<=d<len(self.paths):return
        path=self.paths[d]
        def read():
            values={};errors={}
            for key in ('intensity','gain','trigger','profile'):
                try:values[key]=run_device(path,action='read_'+key)
                except Exception as exc:errors[key]=str(exc)
            return values,errors
        self.task('strengths',read)
    def show_profile(self,profile):
        if profile is None:
            self.loaded_label.configure(text=msg('현재 슬롯 확인 불가 · 직접 선택하세요.','Current slot unavailable · select manually.'));return
        idx=profile['index'];name=profile['name']
        if idx is None:
            text=msg('현재 설정 · 저장 슬롯 정보 없음','Current settings · saved slot unknown')
        else:
            text=msg('현재 슬롯: ','Current slot: ')+f'{idx+1:02d} · '+(name or msg('이름 없음','Unnamed'))
            if profile['edited']:text+=msg(' (수정됨)',' (edited)')
            if 0<=idx<len(self.slots) and self.slots[idx].state=='saved':self.choice.current(idx)
            elif idx>=10:text+=msg(' · 1~10 목록 밖',' · outside slots 1–10')
        self.loaded_label.configure(text=text)
    def extra_number(self,key):
        e=self.extra[key];v=e['value'].get();e['number'].configure(text=f'{round(v*100)}%' if key=='gain' else str(round(v)))
    def extra_task(self,key,write):
        d=self.device.current();e=self.extra[key]
        if self.busy or not self.connected or not 0<=d<len(self.paths) or (write and not e['known']):return
        value=(round(e['value'].get(),2) if key=='gain' else round(e['value'].get())) if write else None
        action=('set_' if write else 'read_')+key
        self.task(key,lambda:run_device(self.paths[d],action=action,value=value))
    def close(self):
        if self.busy:
            self.status.set(msg('장치 응답을 기다린 뒤 닫아 주세요.','Wait for the device operation before closing.'));return
        self.cancel_edit()
        if self.startup_id:self.win.after_cancel(self.startup_id)
        if self.poll_id:self.win.after_cancel(self.poll_id)
        self.win.destroy()
    def invalidate(self,event=None):
        self.cancel_edit();self.confirmed.clear()
        self.loaded_label.configure(text=msg('현재 슬롯 · 미확인','Current slot · unconfirmed'))
        for e in self.extra.values():
            e['known']=False;e['number'].configure(text='—')
            for w in ('scale','read','apply'):e[w].configure(state='disabled')
        self.generation+=1
        self.connected=False;self.intensity_known=False;self.intensity_scale.configure(state='disabled');self.intensity_read.configure(state='disabled');self.intensity_apply.configure(state='disabled');self.intensity_number.configure(text='—');self.slots=[];self.choice.set('');self.choice.configure(values=[],state='disabled');self.apply.configure(state='disabled')
    def selection(self,event=None):
        i=self.choice.current(); enabled=self.connected and not self.busy and 0<=i<len(self.slots) and self.slots[i].state=='saved'
        self.apply.configure(state='normal' if enabled else 'disabled')
    def task(self,kind,fn):
        if self.busy:return
        self.cancel_edit()
        self.generation+=1
        self.busy=True;self.refresh.configure(state='disabled');self.apply.configure(state='disabled');self.device.configure(state='disabled');self.choice.configure(state='disabled')
        self.intensity_scale.configure(state='disabled');self.intensity_apply.configure(state='disabled');self.intensity_read.configure(state='disabled')
        for e in self.extra.values():
            for w in ('scale','read','apply'):e[w].configure(state='disabled')
        self.status.set(msg('처리 중…','Working…'))
        def work():
            try:self.queue.put((kind,fn(),None))
            except Exception as exc:self.queue.put((kind,None,str(exc)))
        threading.Thread(target=work,daemon=True).start()
        if self.poll_id is None:self.poll_id=self.win.after(100,self.poll)
    def discover(self):
        if self.busy:return
        self.invalidate();self.task('devices',devices)
    def read(self):
        i=self.device.current()
        if 0<=i<len(self.paths):self.task('slots',lambda:run_device(self.paths[i]))
    def read_intensity(self):
        d=self.device.current()
        if self.connected and 0<=d<len(self.paths):self.task('intensity',lambda:run_device(self.paths[d],action='read_intensity'))
    def apply_intensity(self):
        d=self.device.current()
        if not self.connected or not self.intensity_known or not 0<=d<len(self.paths):return
        value=round(float(self.intensity_value.get()))
        self.task('intensity',lambda:run_device(self.paths[d],action='set_intensity',value=value))
    def strength_state(self):
        for e in self.extra.values():
            e['read'].configure(state='normal' if self.connected and not self.busy else 'disabled')
            for w in ('scale','apply'):e[w].configure(state='normal' if self.connected and not self.busy and e['known'] else 'disabled')
        self.intensity_read.configure(state='normal' if self.connected and not self.busy else 'disabled')
        state='normal' if self.connected and self.intensity_known and not self.busy else 'disabled'
        self.intensity_scale.configure(state=state);self.intensity_apply.configure(state=state)
    def activate(self):
        if not self.connected:return
        if self.app.engine is not None:
            self.status.set(msg('메인 화면에서 오디오를 정지한 뒤 적용하세요.','Stop audio in the main window before applying.'));return
        i=self.choice.current();d=self.device.current()
        if not (0<=i<len(self.slots) and self.slots[i].state=='saved' and 0<=d<len(self.paths)):return
        self.task('activate',lambda:run_device(self.paths[d],i))
    def poll(self):
        self.poll_id=None
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
                self.connected=any(s.state!='unavailable' for s in result);self.slots=result;self.choice.configure(values=[s.label() for s in result],state='readonly');self.choice.set('');self.selection()
                self.status.set(msg('동글에서 읽었습니다. 목록 선택만으로는 적용되지 않습니다.','Read from dongle. Selecting a row does not apply it.'))
                if self.connected:self.read_strengths()
            elif kind=='strengths':
                values,errors=result
                self.show_profile(values.pop('profile',None))
                errors.pop('profile',None)
                self.connected=bool(values) or self.connected
                for key,value in values.items():
                    self.confirmed[key]=round(value,2) if key=='gain' else value
                    if key=='intensity':self.intensity_known=True;self.intensity_value.set(value)
                    else:self.extra[key]['known']=True;self.extra[key]['value'].set(value)
                self.choice.configure(state='readonly' if self.slots else 'disabled');self.selection()
                self.status.set(msg('강도 준비 완료 · 슬라이더에서 손을 놓으면 적용됩니다.','Strength controls ready. Release a slider to apply.') if not errors else msg('일부 강도 조회 실패 · 새로고침으로 재시도: ','Some controls unavailable; refresh to retry: ')+', '.join(errors))
            elif kind in self.extra:
                self.loaded_label.configure(text=self.loaded_label.cget('text').replace(' (수정됨)','').replace(' (edited)','')+msg(' (수정됨)',' (edited)'))
                self.confirmed[kind]=round(result,2) if kind=='gain' else result
                e=self.extra[kind];e['known']=True;e['value'].set(result);self.selection()
                self.choice.configure(state='readonly' if self.slots else 'disabled')
                self.status.set(msg('현재 동글 설정을 확인했습니다.','Current dongle setting verified.'))
            elif kind=='intensity':
                self.loaded_label.configure(text=self.loaded_label.cget('text').replace(' (수정됨)','').replace(' (edited)','')+msg(' (수정됨)',' (edited)'))
                self.confirmed['intensity']=result
                self.connected=True;self.intensity_known=True;self.intensity_value.set(result);self.strength_state();self.selection()
                self.choice.configure(state='readonly' if self.slots else 'disabled')
                self.status.set(msg('현재 동글 강도: ','Current dongle strength: ')+str(result)+'%')
            else:
                self.invalidate()
                text=msg('적용 완료: ','Applied: ')+result['slot'].label()
                if result['deferred']:text+=msg(' · 전원 재연결 후 유지 여부 미확인',' · Persistence deferred')
                if result['reconnect']:text+=msg(' · USB 설정 반영에 동글 재연결 필요. 재연결 후 다시 조회하세요.',' · Reconnect dongle for USB settings, then refresh.')
                self.status.set(text)
                if not result['reconnect']:self.read_strengths()
        self.strength_state()
        # No idle polling or strength reads. Only pending operations wake this timer.
        if self.busy and self.poll_id is None:self.poll_id=self.win.after(100,self.poll)
