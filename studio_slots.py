"""Studio slot protocol; no save, field-write, firmware or reconnect commands."""
from dataclasses import dataclass
import time

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

def run_device(path,index=None):
    import hid
    d=hid.device()
    try:
        d.open_path(path)
        client=StudioClient(d)
        return client.slots() if index is None else client.activate(index)
    finally: d.close()
