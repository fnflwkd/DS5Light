"""Independent versioned settings with atomic saves and fail-closed reads."""
import copy, hashlib, json
from driver_state import atomic_json
from pathlib import Path
from presets import validate

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

class FeatureStore:
    def __init__(self,path):
        self.path=Path(path);self.error=None
        self.value={'version':1,'games':{},'shortcut':{'enabled':False,'keys':'F13'}}
        try:
            if self.path.exists():
                doc=json.loads(self.path.read_text(encoding='utf-8'));self.validate(doc);self.value=doc
        except Exception as exc:self.error=str(exc)
    @staticmethod
    def validate(doc):
        from mute_shortcut import parse_keys
        if not isinstance(doc,dict) or type(doc.get('version')) is not int or doc.get('version')!=1 or not isinstance(doc.get('games'),dict):raise ValueError('Invalid feature settings')
        s=doc['shortcut']
        if type(s['enabled']) is not bool:raise ValueError('Invalid shortcut switch')
        parse_keys(s['keys'])
        for path,link in doc['games'].items():
            if not isinstance(path,str) or not path or type(link['slot']) is not int or not 0<=link['slot']<12:raise ValueError('Invalid game link')
            if not isinstance(link['hash'],str) or len(link['hash'])!=64:raise ValueError('Invalid game fingerprint')
    def save(self,doc):
        if self.error:raise ValueError('Unreadable feature settings preserved: '+self.error)
        self.validate(doc)
        atomic_json(self.path,doc,allow_nan=False)
        self.value=copy.deepcopy(doc)
    def link(self,path,slot,preset):
        validate(preset);doc=copy.deepcopy(self.value)
        doc['games'][path]={'slot':slot,'hash':fingerprint(preset)};self.save(doc)
    def unlink(self,path):
        doc=copy.deepcopy(self.value);doc['games'].pop(path,None);self.save(doc)
    def resolve(self,path,slots):
        link=self.value['games'].get(path)
        if not link:return None
        preset=slots[link['slot']]
        # Separate-file failure or reused/renamed/deleted slot never applies stale data.
        return copy.deepcopy(preset) if preset and fingerprint(preset)==link['hash'] else None
    def prune(self,slots):
        doc=copy.deepcopy(self.value)
        doc['games']={p:l for p,l in doc['games'].items() if self.resolve(p,slots)}
        self.save(doc)
