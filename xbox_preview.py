"""Opt-in observer of successfully submitted Xbox states; no device or worker."""
import time
from collections import deque
from remapping import BUTTONS
from xbox_source_remap import NAMES
from xbox_turbo import TARGETS

MAPPING=tuple((BUTTONS.index(name),axis,bit) for name,(_,axis,bit) in zip(NAMES,TARGETS))

class XboxPreview:
    def __init__(self):
        self.thread=None;self.enabled=False;self.latest=None;self.last_received=None
        self.events=deque(maxlen=128);self.state=(0,'Xbox 입력 테스트 꺼짐')
    def start(self):
        self.enabled=True;self.events.clear();self.state=(0,'Xbox로 전달한 버튼 입력')
        if self.latest is not None:self._display(*self.latest)
    def stop(self):
        self.enabled=False;self.events.clear();self.state=(0,'Xbox 입력 테스트 꺼짐');self.last_received=None
    def finish(self):
        self.stop();self.latest=None;self.state=(0,'Xbox 모드 종료 · 입력 테스트 종료')
    def publish(self,state,stamp=None):
        item=(state,time.monotonic() if stamp is None else stamp);self.latest=item
        if self.enabled:self._display(*item)
    def _display(self,state,stamp):
        mask=0
        for index,axis,bit in MAPPING:
            active=bool(state[0]&bit) if axis==0 else state[axis]>0
            if active:mask|=1<<index
        if state[0]&0x400:mask|=1<<BUTTONS.index('PS')
        previous=self.state[0]
        for i,name in enumerate(BUTTONS):
            if mask&~previous&(1<<i):self.events.append((stamp,'✕' if name=='×' else name))
        self.state=(mask,'Xbox로 전달한 버튼 입력 · 리맵·터보·토글 적용 후');self.last_received=stamp
