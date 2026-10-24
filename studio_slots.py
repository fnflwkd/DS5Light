"""Studio slot protocol; slot selection and Intensity only; no flash-save or reconnect commands."""
from dataclasses import dataclass
import time
import struct
import math
import threading

_DEVICE_LOCK=threading.Lock()

@dataclass(frozen=True)
class Slot:
    index: int
    state: str
    name: str = ''
    def label(self):
        value = self.name if self.state == 'saved' else ('Empty' if self.state == 'empty' else 'Unavailable')
        return f'{self.index + 1:02d} · {value}'

class StudioClient:
    def __init__(self, device, sleep=time.sleep):
        self.device, self.sleep = device, sleep
    def request(self, command, index, tries=30):
        if command not in (0x0a, 0x09) or not 0 <= index < 10:
            raise ValueError('Invalid slot command')
        packet=bytes([0x80,0x66,command,index])+bytes(60)
        if self.device.send_feature_report(packet)!=64:
            raise RuntimeError('Studio HID write failed')
        for _ in range(tries):
            self.sleep(.06)
            try: raw=bytes(self.device.get_feature_report(0x84,64))
            except OSError: continue
            # hidapi includes the report ID. Never accept an unrelated report.
            if len(raw)<7 or raw[:3]!=bytes([0x84,0x66,command]): continue
            r=raw[1:]
            if r[2]==0xfe or r[3]!=index: continue
            return r
        raise TimeoutError('Studio reply timeout; close the portal and refresh. Activation outcome may be unknown.')
    def intensity_reply(self,command,value=None):
        if command not in (1,4): raise ValueError('Invalid Intensity command')
        args=bytes([0x80,0x66,command,0x13])
        if command==1:
            if type(value) is not int or not 0<=value<=200: raise ValueError('Intensity must be 0–200')
            args+=bytes([value])
        if self.device.send_feature_report(args+bytes(64-len(args)))!=64:
            raise RuntimeError('Studio HID write failed')
        for _ in range(10):
            self.sleep(.06)
            try: raw=bytes(self.device.get_feature_report(0x81,64))
            except OSError: continue
            if len(raw)<5 or raw[:3]!=bytes([0x81,0x66,command]):continue
            if command==4:
                if raw[3]!=0x13:continue
                if raw[4]>200:raise RuntimeError('Invalid Studio Intensity')
                return raw[4]
            if raw[3]!=0:raise RuntimeError('Studio rejected Intensity')
            return None
        raise TimeoutError('Studio response missing; close portal and read again.')
    def intensity(self):
        return self.intensity_reply(4)
    def set_intensity(self,value):
        if type(value) is not int or not 0<=value<=200:raise ValueError('Intensity must be 0–200')
        self.intensity()  # Confirm a responding endpoint immediately before writing.
        self.intensity_reply(1,value)
        actual=self.intensity()
        if actual!=value:raise RuntimeError('Intensity verification failed; read current value again.')
        return actual
    def metadata(self,command):
        if command not in (0x67,0x05):raise ValueError('Invalid metadata command')
        if self.device.send_feature_report(bytes([0x80,0x66,command])+bytes(61))!=64:raise RuntimeError('Studio HID read request failed')
        for _ in range(10):
            self.sleep(.06)
            try:raw=bytes(self.device.get_feature_report(0x81,64))
            except OSError:continue
            if len(raw)>=22 and raw[:3]==bytes([0x81,0x66,command]):return raw
        raise TimeoutError('Studio metadata unavailable')
    def profile(self):
        raw=self.metadata(0x67)
        if raw[3]!=0 or raw[5] not in (0,1):raise RuntimeError('Invalid active profile response')
        return dict(index=None if raw[4]==255 else raw[4],edited=bool(raw[5]),name=raw[6:22].decode('utf-8',errors='replace').rstrip('\0').strip())
    def firmware(self):
        return self.metadata(0x05)[3:].split(b'\0',1)[0].decode('utf-8',errors='replace')
    def battery(self):
        # Identity preflight: real DualSense devices also use Sony's USB IDs.
        self.info(0)
        raw=self.control_packet(4,0x68)[4]
        if raw==0:return None  # Portal also treats 0x00 as no fresh input data.
        level=raw & 15;state=raw >> 4
        if level>10:raise RuntimeError('Invalid Studio battery level')
        return dict(percent=level*10,state=state,raw=raw)
    def control(self,field,value=None):
        # Only the two audited fields are available through this method.
        if field not in (0x01,0xc0):raise ValueError('Unsupported control field')
        if value is not None:
            if field==0x01:
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 1<=value<=2:raise ValueError('Gain must be 1.00–2.00')
                payload=struct.pack('<f',value)
            else:
                if type(value) is not int or not 0<=value<=10:raise ValueError('Reduction must be 0–10')
                payload=bytes([value])
            self.control(field)  # Fresh read before the single write; never retry writes.
            self.control_packet(1,field,payload)
            actual=self.control(field)
            if not math.isclose(actual,value,abs_tol=1e-5):raise RuntimeError('Verification failed; read current value again')
            return actual
        raw=self.control_packet(4,field)
        result=struct.unpack('<f',raw[4:8])[0] if field==1 else raw[4]
        if not math.isfinite(result) or not (1<=result<=2 if field==1 else 0<=result<=10):raise RuntimeError('Invalid or unsupported Studio control')
        return result
    def control_packet(self,command,field,payload=b''):
        packet=bytes([0x80,0x66,command,field])+payload
        if self.device.send_feature_report(packet+bytes(64-len(packet)))!=64:raise RuntimeError('Studio HID write failed')
        for _ in range(10):
            self.sleep(.06)
            try:raw=bytes(self.device.get_feature_report(0x81,64))
            except OSError:continue
            if len(raw)<8 or raw[:3]!=bytes([0x81,0x66,command]):continue
            if command==4 and raw[3]!=field:continue
            if command==1 and raw[3]!=0:raise RuntimeError('Studio rejected control; firmware may not support it')
            return raw
        raise TimeoutError('Studio response missing; close portal and read again')
    def info(self,index):
        r=self.request(0x0a,index,10)
        if r[2]!=0: return Slot(index,'unavailable')
        if len(r)<22 or r[4] not in (0,1): raise RuntimeError('Invalid Studio slot response')
        if not r[4]: return Slot(index,'empty')
        return Slot(index,'saved',r[6:22].decode('utf-8',errors='replace').rstrip('\0').strip())
    def slots(self):
        return [self.info(i) for i in range(10)]
    def activate(self,index):
        # Re-read on the same handle; a stale UI list never authorizes an empty slot.
        slot=self.info(index)
        if slot.state!='saved': raise ValueError('Slot is empty or unavailable')
        r=self.request(0x09,index)
        if r[2] not in (0,2): raise RuntimeError('Studio rejected slot activation')
        if r[4] not in (0,1): raise RuntimeError('Invalid activation response')
        return dict(slot=slot, reconnect=bool(r[4]), deferred=r[2]==2)

def devices():
    import hid
    return [d for d in hid.enumerate(0x054c,0) if d.get('product_id') in (0x0ce6,0x0df2)
            and d.get('usage_page')==1 and d.get('usage') in (4,5)]

def run_device(path,index=None,action=None,value=None):
    # Serialize the shared HID response buffers across settings and battery reads.
    with _DEVICE_LOCK:return _run_device(path,index,action,value)

def _run_device(path,index=None,action=None,value=None):
    import hid
    d=hid.device()
    try:
        d.open_path(path)
        client=StudioClient(d)
        if action=='read_profile':return client.profile()
        if action=='read_firmware':return client.firmware()
        if action=='read_battery':return client.battery()
        if action in ('read_gain','set_gain'):return client.control(0x01,value if action=='set_gain' else None)
        if action in ('read_trigger','set_trigger'):return client.control(0xc0,value if action=='set_trigger' else None)
        if action=='read_intensity':return client.intensity()
        if action=='set_intensity':return client.set_intensity(value)
        return client.slots() if index is None else client.activate(index)
    finally: d.close()
