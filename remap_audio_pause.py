"""UI-thread audio stop/wait/resume scoped to one remap application."""
import time

class AudioPause:
    def __init__(self,panel):
        self.panel=panel;self.app=panel.app;self.engine=self.app.engine;self.resume_error=None
        from xbox_settings_job import bind
        self.xbox_binding=bind(self.app)
        self.path=panel.target();self.selection=self.signature()
        self.errors=getattr(self.engine,'errors',0);self.deadline=time.monotonic()+15
        self.guard=getattr(self.engine,'guard',None)
        self.resume_allowed=not getattr(self.app,'stopping',False) and not self.engine.stop_event.is_set()
        self.app.stop();self.intent=self.app.intent_generation
    def signature(self):
        return tuple(getattr(self.app,name).get() for name in ('source','destination','scope','game','channel') if hasattr(self.app,name))
    def valid(self):
        try:
            from xbox_settings_job import validate
            validate(self.app,self.xbox_binding)
            return not self.app.closing and self.app.intent_generation==self.intent and self.panel.target()==self.path and self.signature()==self.selection
        except (ValueError,AttributeError,RuntimeError):return False
    def wait(self,ready,failed):
        if not self.valid():failed('오디오 재개 요청 취소 · 장치/설정 또는 정지 요청이 바뀌었습니다.');return
        if self.engine.thread and self.engine.thread.is_alive():
            if time.monotonic()>=self.deadline:failed('오디오 종료 시간 초과 · 리맵을 적용하지 않았습니다.');return
            self.panel.status.set('리맵 적용 준비 · 오디오햅틱 종료를 기다립니다…')
            self.app.root.after(50,lambda:self.wait(ready,failed));return
        if self.app.engine is self.engine:
            self.app.last_engine_stats=self.engine.stats();self.app.engine=None;self.app.stopping=False;self.app.last_render=None;self.app.render()
        if self.app.engine is not None:failed('다른 오디오 실행이 시작되어 리맵을 적용하지 않았습니다.');return
        if not self.audio_healthy():failed('오디오 종료 중 오류 또는 장치 연결 끊김 · 리맵을 적용하지 않았습니다.');return
        ready()
    def audio_healthy(self):
        return getattr(self.engine,'errors',0)<=self.errors and (not self.guard or not getattr(self.guard,'error',None) and getattr(self.guard,'connection',None)=='confirmed')
    def resume(self):
        if not self.resume_allowed or not self.valid() or self.app.engine is not None:return False
        if not self.audio_healthy():return False
        try:self.app.start()
        except Exception as exc:
            self.resume_error='오디오 자동 재개 실패: '+str(exc);return False
        return self.app.engine is not None

def restart_pending(app):
    pause=getattr(getattr(app,'remap_panel',None),'audio_pause',None)
    return isinstance(pause,AudioPause) and pause.resume_allowed and pause.valid()

