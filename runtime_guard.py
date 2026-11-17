"""Engine-scoped intent, physical binding and RAM AH checks outside the DSP loop."""
import threading
from studio_slots import devices, run_device, SnapshotChanged
from device_binding import resolve_hid, select_output
from process_list import process_identity

class DeviceTemporarilyAbsent(OSError):
    """Let the existing bounded legacy reconnect loop wait for re-enumeration."""

class RuntimeGuard:
    RECONNECT_INTERVAL = 30
    def __init__(self, stop, preferred=None, pid=None,expected_process=None):
        self.stop=stop;self.preferred=preferred;self.pid=pid
        self.process=process_identity(pid) if pid else None
        if pid and self.process is None:raise RuntimeError('Process identity unavailable')
        if expected_process is not None and self.process!=expected_process:raise RuntimeError('Selected process changed before capture startup')
        self.identity=None;self.output=None;self.input=None
        self.ah=None;self.last_ah=None;self.profile=None;self.connection='unknown'
        self.error=None;self.revision=0;self.monitor=None;self.closed=threading.Event()
        self.reconnect_waiting=threading.Event()
        self.lock=threading.RLock();self.query_lock=threading.RLock()
    def check(self):
        if self.stop.is_set() or self.closed.is_set():raise KeyboardInterrupt()
    def resolve(self):
        with self.query_lock:return self._resolve()
    def _resolve(self):
        self.check();rows=devices()
        selected=self.identity
        if selected is None and self.preferred is not None:
            matches=[r for r in rows if r['path']==self.preferred]
            selected=matches[0] if len(matches)==1 else {'path':self.preferred}
        row=resolve_hid(rows,selected)
        if row is None:
            self.connection='absent' if not rows else 'unknown'
            if not rows and self.output is not None:
                raise DeviceTemporarilyAbsent('Selected Studio device temporarily absent')
            raise RuntimeError('Selected Studio device absent or ambiguous; refresh selection')
        # Missing properties must not erase previously established identity.
        self.identity=dict(row)
        for key in ('serial_number','container_id'):
            if selected and selected.get(key) and not row.get(key):self.identity[key]=selected[key]
        return row
    def refresh(self):
        with self.query_lock:return self._refresh()
    def wait_for_return(self, waiting):
        """Wait only for a previously bound dongle; no new polling thread."""
        if self.output is None:return
        self.reconnect_waiting.set()
        try:
            while True:
                self.check()
                if self.pid and process_identity(self.pid)!=self.process:
                    raise RuntimeError('Selected process exited or identity changed')
                try:
                    self.resolve()
                    return
                except DeviceTemporarilyAbsent:
                    waiting()
                    self.stop.wait(self.RECONNECT_INTERVAL)
        finally:self.reconnect_waiting.clear()
    def _refresh(self):
        row=self.resolve()
        if self.pid and process_identity(self.pid)!=self.process:
            self.stop.set();raise RuntimeError('Selected process exited or identity changed')
        try:
            result=run_device(row['path'],action='read_snapshot',valid=lambda:not self.stop.is_set() and not self.closed.is_set())
        except SnapshotChanged as exc:
            # A metadata race cannot discard a confirmed OFF or authorize ON.
            if exc.ah == 0:
                with self.lock:
                    self.ah=0;self.last_ah=0;self.profile=None;self.revision+=1
            raise
        self.check()
        with self.lock:
            if self.profile!=result['profile']:self.revision+=1
            self.profile=result['profile'];self.ah=result['ah'];self.last_ah=self.ah
            self.connection='confirmed';self.error=None
        return result
    def before_output(self,rows,name=None):
        with self.query_lock:return self._before_output(rows,name)
    def _before_output(self,rows,name=None):
        # Every legacy reopen must obtain new AH/identity evidence.
        self.ah=None;self.revision+=1;self.connection='unknown'
        for attempt in range(3):
            try:self.refresh();break
            except Exception:
                if attempt==2:raise
                self.stop.wait(.25);self.check()
        row=select_output(rows,self.identity,name,self.output)
        if row is None:
            if self.output is not None and self.identity.get('container_id') and not any(
                    r.get('maxOutputChannels',0)>=4 and r.get('container_id')==self.identity['container_id'] for r in rows):
                raise DeviceTemporarilyAbsent('Selected audio endpoint temporarily absent')
            raise RuntimeError('HID/audio physical identity unconfirmed or ambiguous')
        if self.ah==0:raise RuntimeError('RAM AH OFF; enable on device and start again')
        self.output=row;self.check()
        if self.monitor is None:
            self.monitor=threading.Thread(target=self.watch,daemon=True)
            try:self.monitor.start()
            except Exception:
                self.monitor=None;raise
        return row
    def before_input(self,row,channels,rate):
        self.check()
        if self.pid:
            if process_identity(self.pid)!=self.process:raise RuntimeError('Process identity changed')
            return
        key=(row.get('endpoint_id'),row.get('name'),channels,rate,row.get('channel_mask'))
        if self.input is not None and key!=self.input:raise RuntimeError('Capture endpoint or format changed; select and start again')
        if channels==8 and (not row.get('endpoint_id') or row.get('mix_channels')!=8 or row.get('channel_mask')!=0x63f):
            raise RuntimeError('7.1 layout unconfirmed/unsupported; select a verified 0x63f endpoint')
        self.input=key
    def watch(self):
        while not self.closed.wait(2) and not self.stop.is_set():
            if self.reconnect_waiting.is_set():continue
            try:self.refresh()
            except (Exception,KeyboardInterrupt) as exc:
                with self.lock:self.ah=None;self.error=str(exc)
    def allow_output(self):
        self.check()
        # A confirmed OFF remains blocked during a subsequent failed read.
        # Transient read failure otherwise keeps the last confirmed running policy.
        return self.connection=='confirmed' and self.last_ah in (1,2)
    def close(self):
        self.closed.set()
        if self.monitor and self.monitor is not threading.current_thread():self.monitor.join(timeout=3)
    def paused_status(self):
        if self.connection=='confirmed' and self.last_ah==0:return 'RAM AH OFF · transmission paused'
        return 'Device identity unconfirmed · transmission paused'
