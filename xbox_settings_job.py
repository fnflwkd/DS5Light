"""Serialize explicit settings jobs on the Xbox input owner thread."""
import queue
import threading

class Job:
    def __init__(self,fn,readonly=False):
        self.readonly=readonly;self.fn=fn;self.done=threading.Event();self.result=None;self.error=None
    def finish(self,result=None,error=None):
        self.result=result;self.error=error;self.done.set()

class DeviceJobs:
    def __init__(self):self.queue=queue.Queue()
    def submit(self,worker,fn,readonly=False):
        if not worker.alive or worker.phase!='running' or worker.stop_event.is_set():
            raise RuntimeError('Xbox 시작·종료가 끝난 뒤 다시 시도하세요.')
        job=Job(fn,readonly);self.queue.put(job)
        while not job.done.wait(.1):
            if not worker.alive:raise RuntimeError('Xbox 연결이 종료되어 설정 작업이 중단됐습니다.')
        if job.error:raise job.error
        return job.result
    def take(self):
        try:return self.queue.get_nowait()
        except queue.Empty:return None
    def cancel(self):
        while True:
            job=self.take()
            if job is None:return
            job.finish(error=RuntimeError('Xbox 종료로 설정 작업이 취소됐습니다. 다시 조회하세요.'))

def supported(worker):return isinstance(getattr(worker,'settings_jobs',None),DeviceJobs)

def bind(app):
    worker=getattr(getattr(app,'xbox',None),'worker',None)
    return (worker,worker.stop_event) if getattr(worker,'alive',False) is True else (None,None)

def validate(app,binding):
    if getattr(app,'closing',False):raise RuntimeError('프로그램 종료로 설정 작업을 취소했습니다.')
    worker,event=binding
    current=getattr(getattr(app,'xbox',None),'worker',None)
    if worker is not None:
        if current is not worker or worker.stop_event is not event or event.is_set() or not worker.alive or worker.phase!='running':
            raise RuntimeError('Xbox 실행 상태가 바뀌어 설정 작업을 취소했습니다. 다시 조회하세요.')
    elif getattr(current,'alive',False) is True:raise RuntimeError('Xbox 실행 상태가 바뀌었습니다. 다시 시도하세요.')

def run(app,fn,binding=None,readonly=False):
    binding=bind(app) if binding is None else binding
    validate(app,binding)
    worker,event=binding
    if worker is not None:
        if not supported(worker):raise RuntimeError('Xbox를 끈 뒤 설정하세요.')
        def checked():
            validate(app,binding)
            return fn()
        return worker.settings_jobs.submit(worker,checked,readonly=True) if readonly else worker.settings_jobs.submit(worker,checked)
    from xbox_remap_session import pending
    if pending():raise RuntimeError('리맵 복구 기록이 남아 있습니다. 복구 후 다시 조회하세요.')
    return fn()
