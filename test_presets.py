import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from presets import PresetStore, match_game


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'presets.json'
        self.value = dict(name='엘든링 균형', game_exe='eldenring.exe', scope='process', channels=6,
                          input='자동 선택', output='DualSense', controls=dict(mode='normal', bypass=False,
                          strength=.55, background=True, transient=True))

    def test_slots_restart_and_replace(self):
        store = PresetStore(self.path)
        store.save(0, self.value)
        other = copy.deepcopy(self.value); other['name']='다른 게임'; other['channels']=2
        store.save(11, other)
        other['controls']['strength']=.8
        store.save(11, other)
        loaded = PresetStore(self.path)
        self.assertEqual(loaded.slots[0], self.value)
        self.assertEqual(loaded.slots[11], other)
        self.assertIsNone(loaded.slots[1])
        self.assertNotIn('pid', self.path.read_text(encoding='utf-8').lower())

    def test_corrupt_file_preserved(self):
        self.path.write_text('{broken', encoding='utf-8')
        store = PresetStore(self.path)
        with self.assertRaises(ValueError): store.save(0, self.value)
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{broken')

    def test_failed_replace_keeps_previous(self):
        store = PresetStore(self.path); store.save(0, self.value)
        original = self.path.read_bytes()
        with patch('presets.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError): store.save(1, self.value)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIsNone(store.slots[1])
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_values_rejected(self):
        for field, value in [('channels', 8), ('scope', 'all'), ('name', '')]:
            bad = copy.deepcopy(self.value); bad[field] = value
            with self.assertRaises(ValueError): PresetStore(self.path).save(0, bad)
        bad = copy.deepcopy(self.value); bad['controls']['strength'] = float('nan')
        with self.assertRaises(ValueError): PresetStore(self.path).save(0, bad)

    def test_game_relaunch_and_ambiguity(self):
        self.assertEqual(match_game('ELDENRING.exe', [('eldenring.exe', 200)]), 200)
        self.assertIsNone(match_game('eldenring.exe', [('other.exe', 100)]))
        self.assertIsNone(match_game('eldenring.exe', [('eldenring.exe', 200), ('eldenring.exe', 201)]))


if __name__ == '__main__': unittest.main()
