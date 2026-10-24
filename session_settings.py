"""Last PC settings, stored independently from named presets and device settings."""
import json,os,tempfile
from pathlib import Path
from presets import validate

def validate_session(doc):
    if not isinstance(doc,dict) or doc.get('version')!=1:raise ValueError('Invalid last settings version')
    validate(doc['settings'])
    if doc.get('sort') not in ('name','cpu'):raise ValueError('Invalid sort order')
    if type(doc.get('slot')) is not int or not 0<=doc['slot']<12:raise ValueError('Invalid slot')
    if type(doc.get('details')) is not bool:raise ValueError('Invalid details state')
    return doc

class SessionStore:
    def __init__(self,path):
        self.path=Path(path);self.error=None;self.value=None
        try:
            if self.path.exists():self.value=validate_session(json.loads(self.path.read_text(encoding='utf-8')))
        except Exception as exc:self.error=str(exc)
    def save(self,value):
        if self.error:raise ValueError('Unreadable last settings preserved: '+self.error)
        validate_session(value)
        if self.value==value:return
        self.path.parent.mkdir(parents=True,exist_ok=True);name=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path.parent,delete=False) as f:
                name=f.name;json.dump(value,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
            os.replace(name,self.path);self.value=json.loads(json.dumps(value))
        finally:
            if name and Path(name).exists():Path(name).unlink()
