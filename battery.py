"""Low-rate battery polling; no persistent worker, recording, or audio-thread work."""
import queue
import threading
import time
from studio_slots import devices,run_device

class BatteryMonitor:
    INTERVAL=300
    PRESENCE_INTERVAL=300
    def __init__(self,enumerate_devices=devices,read_device=run_device,clock=time.monotonic,wall=time.time):
        self.enumerate=enumerate_devices;self.read=read_device;self.clock=clock;self.wall=wall
        self.queue=queue.Queue();self.busy=False;self.next_check=0;self.last_read=None
        self.path=None;self.preferred=None;self.value=None;self.sampled_at=None
        self.state='waiting';self.force=False
    def refresh(self):
        self.force=True;self.next_check=0
    def tick(self,paused=False,preferred=None):
        try:result=self.queue.get_nowait()
        except queue.Empty:pass
        else:
            self.busy=False
            self.path,self.state,self.value,self.sampled_at,self.last_read=result
            self.next_check=self.clock()+self.PRESENCE_INTERVAL
        if paused or self.busy:return
        now=self.clock()
        if preferred!=self.preferred:
            self.preferred=preferred;self.force=True
        if now<self.next_check and not self.force:return
        path=self.path;last=self.last_read;value=self.value;sampled=self.sampled_at;state=self.state
        force=self.force;self.force=False;self.busy=True
        def work():
            try:
                candidates=[d['path'] for d in self.enumerate()]
                selected=preferred if preferred in candidates else (candidates[0] if len(candidates)==1 and preferred is None else None)
                if selected is None:
                    result=(None,'multiple' if len(candidates)>1 else 'disconnected',None,None,None)
                elif force or selected!=path or last is None or now-last>=self.INTERVAL:
                    data=self.read(selected,action='read_battery')
                    result=(selected,'ready' if data is not None else 'no_data',data,self.wall(),self.clock())
                else:result=(path,state,value,sampled,last)
            except Exception:
                # Never present cached percentage as a current reading on failure.
                result=(None,'unavailable',None,None,None)
            self.queue.put(result)
        threading.Thread(target=work,daemon=True).start()

def battery_text(m,language):
    ko=language=='ko'
    prefix='배터리' if ko else 'Battery'
    hint=' · 클릭하여 갱신' if ko else ' · click to refresh'
    states={'waiting':('조회 대기','waiting'),'multiple':('Studio 설정에서 장치 선택','select device in Studio settings'),
            'disconnected':('연결 없음','disconnected'),'unavailable':('조회 실패','unavailable'),'no_data':('정보 없음','no data')}
    if m.state!='ready':
        return prefix+' · '+states.get(m.state,states['unavailable'])[0 if ko else 1]+hint
    state=m.value['state']
    label={0:('사용 중','on battery'),1:('충전 중','charging'),2:('완충','full'),15:('충전 오류','charge error')}.get(state,('상태 미확인','unknown status'))[0 if ko else 1]
    stamp=time.strftime('%H:%M',time.localtime(m.sampled_at))
    return f"{prefix} {m.value['percent']}% · {label} · {stamp} "+('조회' if ko else 'checked')+hint

def battery_cells(m):
    """None means unknown, not empty. 1–25/26–50/51–75/76–100%."""
    if m.state!='ready' or not m.value:return None
    percent=m.value['percent']
    return max(0,min(4,(percent+24)//25))

import tkinter as tk

class BatteryIcon(tk.Canvas):
    """Static four-cell glyph; redraw only on a changed sample, no timer."""
    def __init__(self,parent,refresh,*,bg,fg,fill):
        super().__init__(parent,width=48,height=22,bg=bg,highlightthickness=0,takefocus=1,cursor='hand2')
        self.colors=(bg,fg,fill);self.previous=object()
        self.bind('<Button-1>',lambda e:refresh())
        self.bind('<Return>',lambda e:refresh())
        self.bind('<space>',lambda e:refresh())
        self.draw(None)
    def show(self,monitor):
        cells=battery_cells(monitor)
        if cells!=self.previous:self.draw(cells)
    def draw(self,cells):
        self.previous=cells;bg,fg,fill=self.colors;self.delete('all')
        self.create_rectangle(2,3,42,19,outline=fg,width=1)
        self.create_rectangle(43,8,46,14,outline=fg,fill=fg)
        if cells is None:
            self.create_text(22,11,text='?',fill=fg,font=('Segoe UI',9))
        else:
            for i in range(4):
                self.create_rectangle(5+i*9,6,11+i*9,16,outline='',fill=fill if i<cells else bg)
