"""Opt-in USB input/rumble forwarding; no configuration or audio DSP changes."""
import threading
import time
from xbox_backend import XboxBackend,pending_cleanup,recover_pending
from xbox_turbo import Turbo
from safe_notify import notify
from xbox_rumble import Rumble,confirm_studio

NEUTRAL=(0,)*7

def axis(value,invert=False):
    delta=value-128
    if delta<0:result=-((-delta*32768+64)//128)
    else:result=(delta*32767+63)//127
    if invert:
        # Preserve exact zero and both signed endpoints.
        if delta<0:result=(-delta*32767+64)//128
        else:result=-((delta*32768+63)//127)
    return result

def decode(raw):
    if len(raw)!=64 or raw[0]!=1:raise ValueError('DualSense USB 64바이트 입력만 지원합니다.')
    hat=raw[8]&15
    if hat>8:raise ValueError('잘못된 방향패드 입력입니다.')
    buttons=0
    for bit,values in ((1,(0,1,7)),(2,(3,4,5)),(4,(5,6,7)),(8,(1,2,3))):
        if hat in values:buttons|=bit
    for value,source,mask in ((0x1000,8,0x20),(0x2000,8,0x40),(0x4000,8,0x10),(0x8000,8,0x80),
                              (0x100,9,1),(0x200,9,2),(0x20,9,0x10),(0x10,9,0x20),
                              (0x40,9,0x40),(0x80,9,0x80),(0x400,10,1)):
        if raw[source]&mask:buttons|=value
    return buttons,raw[5],raw[6],axis(raw[1]),axis(raw[2],True),axis(raw[3]),axis(raw[4],True)

def set_read_mode(device,value):
    if device.set_nonblocking(value)==-1:raise OSError('HID 입력 모드 전환 실패')

def fresh_input(device,cancel):
    """Bounded nonblocking setup drain; continuous reports are not an error."""
    if cancel.is_set():return None
    latest=None;empty=False;deadline=time.monotonic()+.1
    set_read_mode(device,1);read_error=None
    try:
        for _ in range(512):
            if cancel.is_set():return None
            if time.monotonic()>=deadline:break
            raw=device.read(64,0)
            if not raw:empty=True;break
            latest=raw
    except Exception as exc:
        read_error=exc;raise
    finally:
        try:set_read_mode(device,0)
        except Exception as restore_error:
            if read_error is not None:raise RuntimeError(f'{read_error} · 입력 모드 복원 실패: {restore_error}') from read_error
            raise
    if cancel.is_set():return None
    # No empty gap is guaranteed at high polling rates. Use the newest drained
    # report at the bound, rather than failing a healthy continuously busy device.
    raw=latest if latest is not None and not empty else device.read(64,250)
    if cancel.is_set():return None
    decode(raw)
    return raw

class CleanupIssue(str):
    def __new__(cls,kind,message):
        value=super().__new__(cls,message);value.kind=kind;return value

RESTORE_KINDS=frozenset(('hide','access'))

class XboxInput:
    def __init__(self):
        from xbox_preview import XboxPreview
        from xbox_settings_job import DeviceJobs
        self.settings_jobs=DeviceJobs()
        self.preview=XboxPreview()
        self.turbo=Turbo();self.source_active=False;self.source_plan=None;self.source_reason='Xbox 모드를 켜세요.';self.use_hidhide=False;self.report=lambda text:None
        self.thread=None;self.stop_event=threading.Event();self.paused=threading.Event()
        self.phase='idle';self.run_error=None
        self.status='OFF';self.path=None;self.reports=0;self.updates=0;self.cleanup_error=None;self.cleanup_errors=[]
    def notify(self,text):
        # UI logging must not interrupt input or teardown/state publication.
        self.progress_text=text
        notify(self.report,text)
    def set_cleanup_errors(self,errors):
        self.cleanup_errors=list(errors)
        self.cleanup_error=' · '.join(self.cleanup_errors) or None
        self.phase='error' if self.cleanup_error else 'idle'
        self.status=self.cleanup_error or self.run_error or 'OFF'
    def clear_cleanup_kinds(self,kinds):
        self.set_cleanup_errors(e for e in self.cleanup_errors if getattr(e,'kind',None) not in kinds)
    @property
    def alive(self):return bool(self.thread and self.thread.is_alive())
    def start(self,path,device_factory=None,backend_factory=XboxBackend):
        if pending_cleanup():raise RuntimeError('가상 패드 종료가 남아 있습니다. 보조 도구에서 복구하세요.')
        if self.alive:raise RuntimeError('Xbox 모드가 실행 또는 종료 중입니다.')
        self.settings_jobs.cancel();self.turbo.reset();self.preview.finish()
        self.operation_started=time.monotonic();self.progress_text='Xbox 입력 연결 준비'
        self.path=path;self.stop_event=threading.Event();self.paused.clear()
        self.run_error=None;self.phase='starting';self.status='연결 중';self.reports=0;self.updates=0;self.cleanup_error=None;self.cleanup_errors=[]
        self.thread=threading.Thread(target=self.run,args=(path,device_factory,backend_factory),daemon=True)
        try:self.thread.start()
        except Exception:
            self.thread=None;self.phase='idle';self.stop_event.set();raise
    def stop(self):
        self.stop_event.set()
        if self.alive:
            if self.phase!='stopping':self.operation_started=time.monotonic();self.progress_text='Xbox 종료 처리 중'
            self.phase='stopping'
        if self.thread:self.thread.join(timeout=.25)
        if not self.alive and not self.cleanup_error and not self.run_error:self.status='OFF'
    def run(self,path,device_factory,backend_factory):
        device=None;backend=None;rumble=None;hide=None;remap=None;access=False;production=device_factory is None
        try:
            self.notify('Xbox 입력 연결 준비')
            if self.use_hidhide:
                from hidhide import prepare_access,preflight
                if production:hide_expected=preflight()
                if self.stop_event.is_set():return
                access=True;prepare_access();self.notify('원본 입력 접근 허용 완료')
                if self.stop_event.is_set():return
            if device_factory is None:
                import hid
                from studio_slots import devices
                if not any(r['path']==path for r in devices()):raise RuntimeError('선택한 DualSense USB 장치가 없습니다.')
                device_factory=hid.device
            device=device_factory();device.open_path(path);set_read_mode(device,0)
            if production:confirm_studio(device)
            # Confirm format before creating a virtual device.
            first=device.read(64,250)
            decode(first)
            if self.stop_event.is_set():return
            if self.use_hidhide:
                from hidhide import Session
                hide=Session()
                if production:hide.begin(path,expected=hide_expected)
                else:hide.begin(path)
                self.notify('선택 Pico 숨김 설정 완료')
            if self.stop_event.is_set():return
            if production:
                from remapping import MacroClient
                from xbox_remap_session import Session as RemapSession
                self.notify('버튼별 터보용 리맵 확인 · 임시 전환 준비 중')
                remap=RemapSession(path,MacroClient(device))
                self.source_plan=remap.begin();self.source_active=self.source_plan is not None
                self.source_reason=remap.reason
                self.notify('원본 버튼별 처리 준비 완료' if self.source_active else self.source_reason+' 기존 Xbox 입력을 유지합니다.')
                if self.stop_event.is_set():return
            backend=backend_factory();last=None;last_received=time.monotonic()
            rumble=Rumble();backend.set_feedback(rumble.receive)
            raw=fresh_input(device,self.stop_event)
            if self.stop_event.is_set():return
            self.phase='running';was_paused=False;input_key=None;decoded=None;trigger_down=(False,False)
            check_health=getattr(backend,'check_health',lambda:None)
            while not self.stop_event.is_set():
                check_health()
                job=self.settings_jobs.take()
                if job is not None:
                    try:
                        if self.stop_event.is_set():raise RuntimeError('Xbox 종료 요청으로 설정을 취소했습니다.')
                        self.notify('설정 작업 중 · Xbox 입력을 잠시 멈춥니다.')
                        backend.update(NEUTRAL);self.preview.publish(NEUTRAL);self.turbo.reset()
                        rumble.pump(device,time.monotonic(),paused=True)
                        if self.source_plan:self.source_plan.reset()
                        if remap and not job.readonly:
                            remap.close()
                            from xbox_remap_session import pending
                            if pending():raise RuntimeError('다른 리맵 복구 기록이 남아 있습니다. Xbox 종료 후 복구하세요.')
                        if not job.readonly:self.source_active=False;self.source_plan=None
                        if self.stop_event.is_set():raise RuntimeError('Xbox 종료 요청으로 설정을 취소했습니다.')
                        query_error=None
                        try:result=job.fn()
                        except Exception as exc:
                            if not job.readonly:raise
                            result=None;query_error=exc
                        if self.stop_event.is_set():raise RuntimeError('설정 작업 후 Xbox 종료 요청 · 다시 조회하세요.')
                        if remap and not job.readonly:
                            self.source_plan=remap.begin();self.source_active=self.source_plan is not None
                            self.source_reason=remap.reason
                        raw=fresh_input(device,self.stop_event)
                        if self.stop_event.is_set():raise RuntimeError('Xbox 종료 요청 · 설정 결과를 다시 조회하세요.')
                        last=NEUTRAL;decoded=None;input_key=None;trigger_down=(False,False)
                        last_received=time.monotonic();was_paused=False
                        self.notify('조회 실패 · 입력 연결 확인 후 Xbox 유지: '+str(query_error) if query_error else '설정 작업 완료 · Xbox 입력 재개')
                        job.finish(result=result,error=query_error)
                    except Exception as exc:
                        self.phase='stopping';job.finish(error=exc);raise
                    continue
                if raw:
                    if len(raw)!=64 or raw[0]!=1:raise ValueError('잘못된 USB 입력 형식입니다.')
                    key=bytes(raw[1:7])+bytes(raw[8:11])
                    if key!=input_key:decoded=decode(raw);input_key=key
                    state=decoded;trigger_down=(bool(raw[9]&4),bool(raw[9]&8));last_received=time.monotonic();self.reports+=1
                elif time.monotonic()-last_received>.5:
                    raise RuntimeError('패드 입력이 끊겨 Xbox 모드를 정지했습니다. 다시 켜세요.')
                else:state=decoded if self.source_active else None
                if self.paused.is_set():
                    if not was_paused:
                        self.turbo.reset()
                        if self.source_plan:self.source_plan.reset()
                    state=NEUTRAL;self.status='설정 작업 중 · 입력 일시정지';was_paused=True
                elif was_paused:
                    # Discard reports collected during the settings operation.
                    was_paused=False;state=NEUTRAL;decoded=None;input_key=None
                else:
                    self.status='ON · '+('원본 숨김 설정 · ' if self.use_hidhide else '')+'게임 진동 전달 · 동시 사용은 Studio Mix'
                    if state is not None:
                        if self.source_active:state=self.source_plan.process(state,self.turbo,time.monotonic(),trigger_down,raw if raw else None)
                        elif not production:state=self.turbo.apply(state,time.monotonic())
                if state is not None and state!=last:
                    backend.update(state);self.updates+=1;last=state;self.preview.publish(state)
                rumble.pump(device,time.monotonic(),paused=self.paused.is_set())
                # A bounded HID wait yields the thread; no 1ms timer or busy polling.
                raw=device.read(64,8)
        except Exception as exc:
            self.run_error=str(exc);self.status=self.run_error;self.notify('Xbox 작업 오류: '+str(exc))
        finally:
            self.stop_event.set();self.settings_jobs.cancel()
            if self.phase!='stopping':self.operation_started=time.monotonic()
            self.phase='stopping';self.turbo.reset();self.preview.finish();errors=[]
            if backend:
                try:backend.update(NEUTRAL)
                except Exception as exc:self.notify('중립 입력 전송 실패 · 가상 패드 제거를 계속합니다: '+str(exc))
            self.notify('게임 진동 정지 전송 중')
            if rumble:
                try:rumble.close(device)
                except Exception as exc:errors.append(CleanupIssue('rumble','진동 정지 전송 미확인: '+str(exc)))
            if backend:
                self.notify('가상 패드와 진동 수신 종료 중 · 드라이버 응답 대기')
                try:backend.close()
                except Exception as exc:errors.append(CleanupIssue('backend','가상 패드 종료 미확인: '+str(exc)))
            if remap:
                self.notify('Pico 원래 리맵 활성 상태 복원 중')
                try:remap.close()
                except Exception as exc:errors.append(CleanupIssue('remap',str(exc)))
            self.source_active=False;self.source_plan=None
            if device:
                try:device.close()
                except Exception as exc:errors.append(CleanupIssue('device','장치 연결 종료 미확인: '+str(exc)))
            self.notify('원본 패드 숨김·접근 허용 복구 중')
            if hide and not pending_cleanup():
                try:hide.close()
                except Exception as exc:errors.append(CleanupIssue('hide','숨김 복구 실패 · Xbox 창에서 숨김 복구를 누르세요: '+str(exc)))
            if access and not pending_cleanup() and not any(e.kind=='hide' for e in errors):
                try:
                    from hidhide import recover,access_path
                    recover(access_path())
                except Exception as exc:errors.append(CleanupIssue('access','입력 접근 허용 복구 실패: '+str(exc)))
            self.set_cleanup_errors(errors)
            self.notify('Xbox 종료 오류: '+self.cleanup_error if errors else 'Xbox 종료 정리 완료')

    def restore_hiding(self):
        if self.alive:raise RuntimeError('Xbox 종료가 끝난 뒤 복구하세요.')
        def step(kind,action):
            try:result=action()
            except Exception as exc:
                errors=[e for e in self.cleanup_errors if getattr(e,'kind',None)!=kind]
                self.set_cleanup_errors(errors+[CleanupIssue(kind,str(exc))])
                self.notify('복구 실패: '+str(exc))
                raise
            self.clear_cleanup_kinds({kind})
            return result
        step('backend',recover_pending)
        from xbox_remap_session import recover_all as recover_remaps
        failures=[];result=None
        try:step('remap',recover_remaps)
        except Exception as exc:failures.append(exc)
        from hidhide import recover_all
        try:
            result=step('hide',recover_all)
            self.clear_cleanup_kinds({'access'})
        except Exception as exc:failures.append(exc)
        if len(failures)==1:raise failures[0]
        if failures:raise RuntimeError(' · '.join(str(e) for e in failures))
        return result

    def clear_restore_errors(self):
        self.clear_cleanup_kinds(RESTORE_KINDS)
    @property
    def mode_label(self):
        if self.alive:
            if self.stop_event.is_set() or self.phase=='stopping':return '종료 중'
            return 'ON' if self.phase=='running' else '시작 중'
        return '복구 필요' if self.cleanup_error else 'OFF'
