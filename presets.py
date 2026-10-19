"""Versioned PC-only slots. Never persist process IDs or device settings."""
import json
import math
import os
import tempfile
from pathlib import Path

SLOT_COUNT = 12


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('프리셋 형식 오류')
    keys = {'name', 'game_exe', 'scope', 'channels', 'input', 'output', 'controls'}
    if set(value) != keys:
        raise ValueError('프리셋 항목 오류')
    for key in ('name', 'game_exe', 'input', 'output'):
        if not isinstance(value[key], str) or len(value[key]) > 512:
            raise ValueError('프리셋 문자열 오류: '+key)
    if not value['name'].strip() or len(value['name']) > 60:
        raise ValueError('슬롯 이름은 1~60자로 입력하세요')
    if value['scope'] not in ('device', 'process') or type(value['channels']) is not int or value['channels'] not in (2, 6):
        raise ValueError('캡처 범위/채널 오류')
    c = value['controls']
    required = {'mode', 'bypass', 'strength', 'background', 'transient'}
    if not isinstance(c, dict) or not required <= set(c) or set(c) - required - {'rear','lfe','limiter','center'}:
        raise ValueError('필터 설정 형식 오류')
    if c.get('limiter','hard') not in ('hard','soft'):
        raise ValueError('합산 제한 방식 오류')
    if c['mode'] not in ('normal', 'pure'):
        raise ValueError('모드 오류')
    if any(type(c[k]) is not bool for k in ('bypass', 'background', 'transient')):
        raise ValueError('필터 스위치 오류')
    if any(type(c.get(k,False)) is not bool for k in ('rear','lfe','center')):
        raise ValueError('채널 스위치 오류')
    if type(c['strength']) not in (float, int) or not math.isfinite(c['strength']) or not 0 <= c['strength'] <= 1:
        raise ValueError('억제 강도 범위 오류')
    return value


def match_game(exe, candidates):
    """No arbitrary PID when multiple instances share a name."""
    matches = [pid for name, pid in candidates if exe and name.casefold() == exe.casefold()]
    return matches[0] if len(matches) == 1 else None


class PresetStore:
    def __init__(self, path):
        self.path = Path(path)
        self.slots = [None] * SLOT_COUNT
        self.error = None
        try:
            if self.path.exists():
                doc = json.loads(self.path.read_text(encoding='utf-8'))
                if doc.get('version') not in (1,2,3,4) or not isinstance(doc.get('slots'), list) or len(doc['slots']) != SLOT_COUNT:
                    raise ValueError('지원하지 않는 프리셋 파일 형식')
                for item in doc['slots']:
                    if item is not None:
                        validate(item)
                self.slots = doc['slots']
        except Exception as exc:
            self.error = str(exc)

    def save(self, index, value):
        if self.error:
            raise ValueError('기존 파일을 읽지 못해 덮어쓰기를 막았습니다: '+self.error)
        if not 0 <= index < SLOT_COUNT:
            raise ValueError('슬롯 번호 오류')
        validate(value)
        slots = list(self.slots)
        slots[index] = json.loads(json.dumps(value, allow_nan=False))
        payload = json.dumps({'version': 4, 'slots': slots}, ensure_ascii=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        old_version=json.loads(self.path.read_text(encoding='utf-8')).get('version') if self.path.exists() else None
        if old_version in (1,2,3):
            backup=self.path.with_name(self.path.stem+f'.v{old_version}.backup.json')
            if not backup.exists():
                with backup.open('xb') as f: f.write(self.path.read_bytes())
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as f:
                name = f.name
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
            self.slots = slots
        finally:
            if name and Path(name).exists():
                Path(name).unlink()
