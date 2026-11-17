"""Last PC settings, stored independently from named presets and device settings."""
import json
from driver_state import atomic_json
from pathlib import Path
from presets import validate

def validate_session(doc):
    if not isinstance(doc,dict) or type(doc.get('version')) is not int or doc.get('version') not in (1,2):raise ValueError('Invalid last settings version')
    validate(doc['settings'])
    if doc.get('sort') not in ('name','cpu','audio'):raise ValueError('Invalid sort order')
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
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists() and value['version']==2:
            old=json.loads(self.path.read_text(encoding='utf-8'))
            backup=self.path.with_name(self.path.stem+'.v1.backup.json')
            if old.get('version')==1 and not backup.exists():
                with backup.open('xb') as f:f.write(self.path.read_bytes())
        atomic_json(self.path,value,allow_nan=False)
        self.value=json.loads(json.dumps(value))
