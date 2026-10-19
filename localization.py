"""UI-only localization. No dependency from the audio processing thread."""
import ctypes
import json
import locale
import os
from pathlib import Path
import sys
import tempfile
from translations import EN

AUTO_KO = '자동 선택 · 기존 BAT 방식'

def settings_path():
    if '--ui-test-path' in sys.argv:
        return Path(sys.argv[sys.argv.index('--ui-test-path') + 1])
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'DS5Light' / 'ui.json'

def system_language():
    try:
        if os.name == 'nt':
            return 'ko' if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff == 0x12 else 'en'
        return 'ko' if (locale.getlocale()[0] or '').startswith('ko') else 'en'
    except Exception:
        return 'en'

def load_language(path=None):
    try:
        value=json.loads((path or settings_path()).read_text(encoding='utf-8'))['language']
        if value in ('ko','en'): return value
    except (OSError,ValueError,KeyError,TypeError):
        pass
    return system_language()

def save_language(value,path=None):
    if value not in ('ko','en'): raise ValueError('Unsupported language')
    path=path or settings_path()
    # Preserve unrelated preferences and never overwrite unreadable user data.
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(data,dict): raise ValueError('Invalid UI settings file')
    data['language']=value
    path.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as f:
            name=f.name; json.dump(data,f,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if name and Path(name).exists(): Path(name).unlink()

LANGUAGE = sys.argv[sys.argv.index('--language')+1] if '--language' in sys.argv else load_language()
if LANGUAGE not in ('ko','en'): LANGUAGE=system_language()
ORDERED = sorted(EN,key=len,reverse=True)

def tr(text):
    if LANGUAGE=='ko': return text
    if text in EN: return EN[text]
    # Dynamic messages contain device names / numbers; translate known fragments only.
    for key in ORDERED:
        if key in text: text=text.replace(key,EN[key])
    return text

def canonical_device(value):
    return AUTO_KO if value in (AUTO_KO, EN[AUTO_KO]) else value

def display_device(value):
    return tr(AUTO_KO) if canonical_device(value)==AUTO_KO else value
