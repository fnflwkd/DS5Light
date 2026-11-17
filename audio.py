"""0.2: original bridge transport + optional output DSP. No recording/network."""
import ast
import os
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
from windows_audio import attach_endpoint_ids
from runtime_guard import RuntimeGuard, DeviceTemporarilyAbsent
from stereo_duplicate import StereoDuplicator

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

def install_duplicate(ns):
    """One mapper per engine namespace; keep every other original mapping."""
    original=ns['map_stereo_to_4ch'];duplicator=StereoDuplicator()
    def mapped(data,mode):
        return duplicator.process(data) if mode=='duplicate' else original(data,mode)
    ns['map_stereo_to_4ch']=mapped
    return duplicator

def devices():
    p=pa.PyAudio()
    try:
        api=p.get_host_api_info_by_type(pa.paWASAPI)['index']
        return attach_endpoint_ids([dict(d) for d in p.get_device_info_generator() if d['hostApi']==api])
    finally: p.terminate()

def bridge_conflict():
    # Skip shell startup only when native enumeration proves no other Python candidate.
    try:
        from process_list import processes
        candidates=[pid for name,pid in processes() if pid!=os.getpid() and name.lower().startswith('python') and name.lower().endswith('.exe')]
    except Exception:candidates=None
    if candidates==[]:return
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
    def __init__(self): self.processor=None; self.last_policy=None
    def prepare(self, controls):
        if controls.mode=='normal' and not controls.bypass and self.processor is None:
            self.processor=Processor()
    def process(self, data, controls):
        if controls.mode=='pure':
            self.last_policy='pure'
            return bytes(len(data))
        if controls.mode!='normal': raise ValueError('알 수 없는 모드')
        if controls.bypass:
            self.last_policy='bypass'
            return data  # exact original bytes, no fade, quantizer, filter, or ring
        if self.processor is None or self.last_policy in ('bypass','pure'):
            self.processor=Processor()
        self.last_policy='filtered'
        x=np.frombuffer(data,'<i2').reshape(-1,4)[:,:2].astype(np.float32)/32768
        out=np.empty_like(x)
        for i in range(0,len(x),240):
            out[i:i+240]=self.processor.process(x[i:i+240],controls,now=time.perf_counter())
        pcm=np.clip(np.rint(out*32768),-32768,32767).astype('<i2')
        return np.tile(pcm,(1,2)).tobytes()

class Engine:
    def __init__(self,input_name=None,output_name=None,controls=Controls(),silent=False,process_pid=None,process_channels=6,studio_path=None,expected_process=None):
        self.input_name,self.output_name=input_name,output_name
        self.controls,self.silent=controls,silent
        self.provider=RumbleStateProvider()
        self.stop_event=threading.Event(); self.finished=threading.Event(); self.thread=None
        self.status='대기'; self.times=deque(maxlen=12000)
        self.blocks=0; self.errors=0; self.peak=0.; self.latencies={}; self.opens=[]
        self.output_processor=OutputProcessor()
        self.process_pid,self.process_channels=process_pid,process_channels
        self.expected_process=expected_process
        self.process_stream=None
        self.capture_channels=None
        self.capture_queue_ms=deque(maxlen=2048);self.write_ms=deque(maxlen=2048)
        self.capture_layout=None;self.studio_path=studio_path;self.guard=None
        self.phase="idle";self.startup_steps_ms={}
        self.desired_controls=controls;self.filter_thread=None;self.filter_ready=None
        self.filter_error=None;self.filter_preparing=False
    def request_controls(self, controls):
        """UI-thread request. Cold filter construction never runs in Stream.write."""
        self.desired_controls=controls
        if controls.bypass or controls.mode!='normal' or (self.output_processor.processor is not None
                and self.controls.mode=='normal' and not self.controls.bypass
                and self.output_processor.last_policy not in ('bypass','pure')):
            self.controls=controls
            return
        if self.filter_ready is not None or self.filter_preparing:return
        self.filter_preparing=True;self.filter_error=None
        def prepare():
            try:
                processor=Processor()
                if not self.stop_event.is_set():self.filter_ready=processor
            except Exception as exc:self.filter_error=str(exc)
            finally:self.filter_preparing=False
        self.filter_thread=threading.Thread(target=prepare,daemon=True)
        try:self.filter_thread.start()
        except Exception as exc:self.filter_preparing=False;self.filter_error=str(exc)
    def apply_prepared_controls(self):
        processor=self.filter_ready
        if processor is not None and not self.stop_event.is_set():
            self.filter_ready=None
            self.output_processor.processor=processor
            self.output_processor.last_policy=None
            self.controls=self.desired_controls

    def measure_startup(self,name,fn):
        started=time.perf_counter()
        try:return fn()
        finally:self.startup_steps_ms[name]=round((time.perf_counter()-started)*1000,3)
    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.phase="starting"
        self.thread=threading.Thread(target=self._worker,daemon=True)
        try:self.thread.start()
        except Exception:
            self.thread=None;self.phase='finished';self.finished.set();raise
    def _worker(self):
        try:self._run()
        except Exception as exc:
            self.status='오류: '+str(exc);self.errors+=1
        finally:
            if self.process_pid:
                try:
                    from process_audio import recover_pending
                    if self.process_stream:self.process_stream.close()
                    recover_pending()
                except Exception as exc:
                    self.status='오류: '+str(exc);self.errors+=1
            self.phase='finished'
            self.finished.set()
    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=4)
        return not self.thread or not self.thread.is_alive()
    def stats(self):
        a=list(self.times)
        return dict(status=self.status,blocks=self.blocks,errors=self.errors,peak=self.peak,startup_steps_ms=dict(self.startup_steps_ms),
            dsp_ms=dict(zip(('p50','p95','p99','max'),np.percentile(a,[50,95,99,100]).tolist())) if a else {},
            stream_latency=self.latencies,transport='legacy int16 / 480 / blocking',
            drop_underrun='원본 방식: 드라이버 손실 횟수 계측 안 함',pure=self.provider.status,
            process_pid=self.process_pid,process_channels=self.process_channels if self.process_pid else None,
            capture_channels=self.capture_channels,capture_layout=self.capture_layout,phase=self.phase,
            ah=self.guard.ah if self.guard else None,last_ah=self.guard.last_ah if self.guard else None,
            capture_queue_ms=self._summary(self.capture_queue_ms),output_write_ms=self._summary(self.write_ms),
            latency_note="Driver estimates and queue/write timings; not acoustic-to-haptic latency",
            process_drop=self.process_stream.drops if self.process_stream else 0,
            process_stale=self.process_stream.stale if self.process_stream else 0)
    @staticmethod
    def _summary(values):
        return dict(zip(('p50','p95','p99','max'),np.percentile(list(values),[50,95,99,100]).tolist())) if values else {}
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
                while True:
                    if engine.guard.connection=='absent':
                        raise DeviceTemporarilyAbsent('Controller disconnected')
                    available=self.stream.get_read_available()
                    if available>=n:break
                    engine._check(); engine.stop_event.wait(.001)
                engine.capture_queue_ms.append(1000*available/self.kwargs['rate'])
                engine._check()
                data=self.stream.read(n,**kwargs)
                controls=engine.controls
                return self.channel_mixer.process(data,self.kwargs['channels'],self.kwargs['rate'],controls.rear,controls.lfe,controls.limiter,center=controls.center)
            def write(self,data,**kwargs):
                engine._check(); start=time.perf_counter()
                if engine.guard.connection=='absent':
                    raise DeviceTemporarilyAbsent('Controller disconnected')
                engine.apply_prepared_controls()
                processing_error=None
                try: out=engine.output_processor.process(data,engine.controls)
                except Exception as exc:
                    engine.errors+=1;processing_error='필터 오류: 무음 '+str(exc);out=bytes(len(data))
                engine.times.append((time.perf_counter()-start)*1000)
                if engine.silent: out=bytes(len(out))
                engine._check()
                if not engine.guard.allow_output():
                    engine.status=engine.guard.paused_status();return
                engine.status=processing_error or ('RAM AH unconfirmed · last confirmed ON' if engine.guard.error else 'Running · RAM AH ON')
                if engine.filter_preparing:engine.status+=' · 필터 준비 중 · 기존 출력 유지'
                elif engine.filter_error:engine.status+=' · 필터 준비 실패: '+engine.filter_error
                write_start=time.perf_counter()
                self.stream.write(out,**kwargs)
                engine.write_ms.append((time.perf_counter()-write_start)*1000)
                engine.blocks+=1
                if data:
                    engine.peak=float(np.max(np.abs(np.frombuffer(data,'<i2').astype(np.int32))))/32768
        class PA:
            def __init__(self):
                if engine.guard:
                    def waiting():
                        engine.phase='reconnecting'
                        engine.status='Disconnected · waiting to reconnect (Stop cancels)'
                    engine.guard.wait_for_return(waiting)
                self.actual=engine.measure_startup('portaudio_init',pa.PyAudio)
                api=self.actual.get_host_api_info_by_type(pa.paWASAPI)['index']
                self.rows=attach_endpoint_ids([dict(d) for d in self.actual.get_device_info_generator() if d['hostApi']==api])
            def __getattr__(self,name): return getattr(self.actual,name)
            def get_device_info_by_index(self,index):
                if index==-7007:
                    return dict(name='게임 PID '+str(engine.process_pid),defaultSampleRate=48000,maxInputChannels=engine.process_channels)
                return next((d for d in self.rows if d['index']==index),self.actual.get_device_info_by_index(index))
            def open(self,**kwargs):
                engine._check()
                if kwargs.get('output'):
                    row=engine.measure_startup('device_confirmation',lambda:engine.guard.before_output(self.rows,engine.output_name))
                    kwargs['output_device_index']=row['index']
                if kwargs.get('input'):
                    row=self.get_device_info_by_index(kwargs['input_device_index'])
                    engine.guard.before_input(row,kwargs['channels'],kwargs['rate'])
                    engine.capture_layout=(0x63f if kwargs['channels']==8 else 0x3f if kwargs['channels']==6 else 3) if engine.process_pid else row.get('channel_mask')
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
                s=engine.measure_startup('output_open' if kwargs.get('output') else 'input_open',lambda:self.actual.open(**kwargs))
                engine.opens.append(dict(kwargs)); engine.opens=engine.opens[-8:]
                if kwargs.get('input'): engine.latencies['input_s']=s.get_input_latency()
                else:
                    engine.latencies['output_s']=s.get_output_latency()
                    engine.status='연결됨 · 기존 브리지 전송'+(' · 무음 시험' if engine.silent else '')
                    if engine.process_pid: engine.status='게임 전용 PID '+str(engine.process_pid)+(' · 무음 시험' if engine.silent else '')
                if engine.stop_event.is_set():
                    s.close();engine._check()
                engine.phase="running"
                return Stream(s,kwargs)
        class PAModule:
            PyAudio=PA
            def __getattr__(self,name): return getattr(pa,name)
        class Clock:
            def time(self): engine._check(); return time.time()
            def sleep(self,seconds):
                engine.stop_event.wait(seconds); engine._check()
        ns=original_namespace(PAModule()); ns['time']=Clock()
        install_duplicate(ns)
        if self.process_pid:
            # Legacy reconnect code can fall back to the default device. Never
            # permit that when process isolation was requested.
            ns['find_loopback_by_name']=lambda p,name:-7007
            ns['find_default_loopback']=lambda p:-7007
        try:
            self.measure_startup('bridge_check',bridge_conflict);self._check()
            self.measure_startup('filter_prepare',lambda:self.output_processor.prepare(self.controls));self._check()
            self.guard=RuntimeGuard(self.stop_event,self.studio_path,self.process_pid,expected_process=self.expected_process)
            ds=self.measure_startup('audio_device_list',devices)
            # Selection is constrained on every open, including legacy retries.
            def output_index(p,debug=False):
                self._check()
                from device_binding import select_output
                try:row=self.guard.resolve()
                except (RuntimeError,DeviceTemporarilyAbsent):return None  # Preserve bounded discovery/reconnect.
                output=select_output(p.rows,row,self.output_name,self.guard.output)
                return output['index'] if output else None
            ns['find_dongle_output']=output_index
            if not self.process_pid:
                original_default=ns['find_default_loopback']
                def input_index(p,name=None):
                    if self.guard.input:
                        endpoint,old_name,*_=self.guard.input
                        matches=[d for d in p.rows if d.get('isLoopbackDevice') and (d.get('endpoint_id')==endpoint if endpoint else d['name']==old_name)]
                        if len(matches)!=1:raise RuntimeError('Selected input unavailable; no default fallback')
                        return matches[0]['index']
                    return original_default(p)
                ns['find_loopback_by_name']=input_index
                ns['find_default_loopback']=input_index
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
        except KeyboardInterrupt: self.status='정지'+(': '+self.guard.error if self.guard and self.guard.error else '')
        except Exception as exc: self.status='오류: '+str(exc); self.errors+=1
        finally:
            self.phase='finished'
            if self.guard:self.guard.close()

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
