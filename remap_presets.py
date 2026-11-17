"""Four local macro presets; atomic writes, no HID access."""
import json
import os
import tempfile
from pathlib import Path

class RemapPresets:
    def __init__(self,path):
        self.path=Path(path);self.slots=[None]*4;self.error=None
        try:
            if self.path.exists():
                doc=json.loads(self.path.read_text(encoding='utf-8'))
                self.validate(doc);self.slots=doc['slots']
        except Exception as e:self.error=str(e)
    @staticmethod
    def validate(doc):
        if not isinstance(doc,dict) or type(doc.get('version')) is not int or doc.get('version')!=1 or not isinstance(doc.get('slots'),list) or len(doc['slots'])!=4:
            raise ValueError('프리셋 파일 형식 오류')
        for slot in doc['slots']:
            if slot is None:continue
            if not isinstance(slot,dict) or not isinstance(slot.get('name'),str) or not 1<=len(slot['name'])<=24:raise ValueError('프리셋 이름 오류')
            if type(slot.get('disabled')) is not int or not 0<=slot['disabled']<=0xffffffff:raise ValueError('프리셋 사용 설정 오류')
            rows=slot.get('rows')
            if not isinstance(rows,list) or len(rows)!=32:raise ValueError('프리셋 행 개수 오류')
            for row in rows:
                if not isinstance(row,str) or len(row)!=70 or len(bytes.fromhex(row))!=35:raise ValueError('프리셋 데이터 오류')
    def save(self,index,name,rows,disabled):
        if self.error:raise ValueError('손상된 프리셋 파일을 보존하기 위해 저장 차단: '+self.error)
        if type(index) is not int or not 0<=index<4:raise ValueError('프리셋 번호 오류')
        slots=list(self.slots);slots[index]=dict(name=name.strip(),rows=[r.hex() for r in rows],disabled=disabled)
        doc=dict(version=1,slots=slots);self.validate(doc)
        self.path.parent.mkdir(parents=True,exist_ok=True);temp=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',dir=self.path.parent,delete=False) as f:
                temp=f.name;json.dump(doc,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
            os.replace(temp,self.path);self.slots=slots
        finally:
            if temp and Path(temp).exists():Path(temp).unlink()
    def load(self,index):
        if self.error:raise ValueError('프리셋 파일 오류: '+self.error)
        if type(index) is not int or not 0<=index<4:raise ValueError('프리셋 번호 오류')
        slot=self.slots[index]
        if slot is None:raise ValueError('빈 프리셋입니다. 현재 편집을 먼저 저장하세요.')
        return [bytes.fromhex(r) for r in slot['rows']],slot['disabled']
