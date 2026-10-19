"""0.2: original bridge transport + optional output DSP. No recording/network."""
import ast
import ctypes
import io
import json
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pyaudiowpatch as pa
from core import Controls, Processor, RumbleStateProvider
from process_audio import ProcessCaptureStream
from channel_mix import ChannelMixer

ORIGINAL = Path(__file__).parent/'vendor/ds5audio_original.py'

def original_namespace(pyaudio_module=pa):
    # Keep original functions/constants verbatim. Omit launcher-only imports-in-try,
    # __main__, and pythonw logging redirection; the GUI owns lifecycle/logging.
    tree = ast.parse(ORIGINAL.read_text(encoding='utf-8'), filename=str(ORIGINAL))
    tree.body = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef))]
    ns = {'__name__':'ds5audio_embedded', 'pyaudio':pyaudio_module}
    exec(compile(tree,str(ORIGINAL),'exec'),ns)
    ns['pyaudio'] = pyaudio_module
    ns['print'] = lambda *a,**k: None
    ns['sys'] = SimpleNamespace(stderr=io.StringIO())
    return ns

def devices():
    p=pa.PyAudio()
    try:
        api=p.get_host_api_info_by_type(pa.paWASAPI)['index']
        return [dict(d) for d in p.get_device_info_generator() if d['hostApi']==api]
    finally: p.terminate()

def bridge_conflict():
    command = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python.*\\.exe$' -and $_.CommandLine -match '(?i)(?:[\\\\/]|[\"\\s])ds5audio\\.py(?=[\"\\s]|$)' } | Select-Object ProcessId,Name | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,timeout=8,creationflags=0x08000000)
    if result.returncode: raise RuntimeError('기존 브리지 조회 실패. 프로세스 조회 권한을 확인하세요.')
    if result.stdout.strip(): raise RuntimeError('기존 ds5audio.py 실행 중: 기존 창에서 먼저 종료하세요.')

class InstanceLock:
    def __init__(self):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
        self.kernel.CreateMutexW.restype=ctypes.c_void_p
        self.handle=self.kernel.CreateMutexW(None,False,'Local\\DS5LightPreprocessor-v1')
        if not self.handle or ctypes.get_last_error()==183:
            if self.handle: self.close()
            raise RuntimeError('전처리기가 이미 실행 중입니다.')
    def close(self):
        if self.handle:
            self.kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            self.kernel.CloseHandle(self.handle); self.handle=None

class OutputProcessor:
    """Input is the original bridge's final interleaved 4ch int16 bytes."""
    def __init__(self): self.processor=Processor(); self.last_policy=None
    def process(self, data, controls):
        if controls.mode=='pure':
            self.last_policy='pure'
            return bytes(len(data))
        if controls.mode!='normal': raise ValueError('알 수 없는 모드')
        if controls.bypass:
            self.last_policy='bypass'
            return data  # exact original bytes, no fade, quantizer, filter, or ring
        if self.last_policy in ('bypass','pure'):
            self.processor=Processor()
        self.last_policy='filtered'
        x=np.frombuffer(data,'<i2').reshape(-1,4)[:,:2].astype(np.float32)/32768
        out=np.empty_like(x)
        for i in range(0,len(x),240):
            out[i:i+240]=self.processor.process(x[i:i+240],controls,now=time.perf_counter())
        pcm=np.clip(np.rint(out*32768),-32768,32767).astype('<i2')
        return np.tile(pcm,(1,2)).tobytes()

class Engine:
    def __init__(self,input_name=None,output_name=None,controls=Controls(),silent=False,process_pid=None,process_channels=6):
        self.input_name,self.output_name=input_name,output_name
        self.controls,self.silent=controls,silent
        self.provider=RumbleStateProvider()
        self.stop_event=threading.Event(); self.thread=None
        self.status='대기'; self.times=deque(maxlen=12000)
        self.blocks=0; self.errors=0; self.peak=0.; self.latencies={}; self.opens=[]
        self.output_processor=OutputProcessor()
        self.process_pid,self.process_channels=process_pid,process_channels
        self.process_stream=None
        self.capture_channels=None
    def start(self):
        if self.thread and self.thread.is_alive(): return
        bridge_conflict()
        self.thread=threading.Thread(target=self._run,daemon=True); self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=4)
        return not self.thread or not self.thread.is_alive()
    def stats(self):
        a=list(self.times)
        return dict(status=self.status,blocks=self.blocks,errors=self.errors,peak=self.peak,
            dsp_ms=dict(zip(('p50','p95','p99','max'),np.percentile(a,[50,95,99,100]).tolist())) if a else {},
            stream_latency=self.latencies,transport='legacy int16 / 480 / blocking',
            drop_underrun='원본 방식: 드라이버 손실 횟수 계측 안 함',pure=self.provider.status,
            process_pid=self.process_pid,process_channels=self.process_channels if self.process_pid else None,
            capture_channels=self.capture_channels,
            process_drop=self.process_stream.drops if self.process_stream else 0,
            process_stale=self.process_stream.stale if self.process_stream else 0)
    def _check(self):
        if self.stop_event.is_set(): raise KeyboardInterrupt()
    def _run(self):
        engine=self
        class Stream:
            def __init__(self,stream,kwargs):
                self.stream,self.kwargs=stream,kwargs
                self.channel_mixer=ChannelMixer()
                if kwargs.get('input'): engine.capture_channels=kwargs['channels']
            def __getattr__(self,name): return getattr(self.stream,name)
            def read(self,n,**kwargs):
                # Only a cancellable wait; read size/data/PortAudio policy unchanged.
                while self.stream.get_read_available()<n:
                    engine._check(); engine.stop_event.wait(.001)
                engine._check()
                data=self.stream.read(n,**kwargs)
                controls=engine.controls
                return self.channel_mixer.process(data,self.kwargs['channels'],self.kwargs['rate'],controls.rear,controls.lfe,controls.limiter,center=controls.center)
            def write(self,data,**kwargs):
                engine._check(); start=time.perf_counter()
                try: out=engine.output_processor.process(data,engine.controls)
                except Exception as exc:
                    engine.errors+=1; engine.status='필터 오류: 무음 '+str(exc); out=bytes(len(data))
                engine.times.append((time.perf_counter()-start)*1000)
                if engine.silent: out=bytes(len(out))
                self.stream.write(out,**kwargs)
                engine.blocks+=1
                if data:
                    engine.peak=float(np.max(np.abs(np.frombuffer(data,'<i2').astype(np.int32))))/32768
        class PA:
            def __init__(self): self.actual=pa.PyAudio()
            def __getattr__(self,name): return getattr(self.actual,name)
            def get_device_info_by_index(self,index):
                if index==-7007:
                    return dict(name='게임 PID '+str(engine.process_pid),defaultSampleRate=48000,maxInputChannels=engine.process_channels)
                return self.actual.get_device_info_by_index(index)
            def open(self,**kwargs):
                engine._check()
                if engine.process_pid and kwargs.get('input') and kwargs.get('input_device_index')!=-7007:
                    raise RuntimeError('게임 전용에서 장치 전체 캡처로 전환하려는 경로를 차단했습니다')
                if kwargs.get('input') and kwargs.get('input_device_index')==-7007:
                    engine.process_stream=ProcessCaptureStream(engine.process_pid,engine.process_channels)
                    engine.latencies['input_s']=None
                    return Stream(engine.process_stream,kwargs)
                if kwargs.get('input'):
                    d=self.actual.get_device_info_by_index(kwargs['input_device_index'])
                    if 'dualsense' in d['name'].lower():
                        raise OSError('자기 출력 재캡처 차단')
                s=self.actual.open(**kwargs)
                engine.opens.append(dict(kwargs)); engine.opens=engine.opens[-8:]
                if kwargs.get('input'): engine.latencies['input_s']=s.get_input_latency()
                else:
                    engine.latencies['output_s']=s.get_output_latency()
                    engine.status='연결됨 · 기존 브리지 전송'+(' · 무음 시험' if engine.silent else '')
                    if engine.process_pid: engine.status='게임 전용 PID '+str(engine.process_pid)+(' · 무음 시험' if engine.silent else '')
                return Stream(s,kwargs)
        class PAModule:
            PyAudio=PA
            def __getattr__(self,name): return getattr(pa,name)
        class Clock:
            def time(self): engine._check(); return time.time()
            def sleep(self,seconds):
                engine.stop_event.wait(seconds); engine._check()
        ns=original_namespace(PAModule()); ns['time']=Clock()
        if self.process_pid:
            # Legacy reconnect code can fall back to the default device. Never
            # permit that when process isolation was requested.
            ns['find_loopback_by_name']=lambda p,name:-7007
            ns['find_default_loopback']=lambda p:-7007
        try:
            ds=devices()
            def index(name,is_input):
                if name is None: return None
                found=[d for d in ds if d['name']==name and (d.get('isLoopbackDevice') if is_input else d['maxOutputChannels']>=4)]
                if len(found)!=1: raise RuntimeError('선택한 장치 없음/중복: 다시 선택하세요')
                return found[0]['index']
            args=SimpleNamespace(list=False,in_index=-7007 if self.process_pid else index(self.input_name,True),out_index=index(self.output_name,False),
                capture_name=None,auto_capture=False,wait_device=30.,map='duplicate',verbose=False)
            code=ns['run'](args)
            if code: self.status='브리지 오류: '+ns['sys'].stderr.getvalue()[-600:]; self.errors+=1
            else: self.status='정지'
        except KeyboardInterrupt: self.status='정지'
        except Exception as exc: self.status='오류: '+str(exc); self.errors+=1

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--list',action='store_true')
    parser.add_argument('--silent-probe',type=float,default=0)
    args=parser.parse_args()
    if args.list: print(json.dumps(devices(),ensure_ascii=False,indent=2))
    elif args.silent_probe:
        lock=InstanceLock(); e=Engine(controls=Controls(bypass=True),silent=True)
        try: e.start(); time.sleep(min(args.silent_probe,30))
        finally:
            e.stop(); print(json.dumps(e.stats(),ensure_ascii=False,indent=2)); lock.close()
