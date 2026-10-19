import unittest, tempfile, json
from pathlib import Path
from unittest.mock import patch
import localization as L
from translations import EN
from presets import PresetStore

class LocalizationTests(unittest.TestCase):
    def test_preferences_roundtrip_and_preserve_other_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ui.json'; p.write_text('{"other": 7}')
            for lang in ('en','ko'):
                L.save_language(lang,p)
                self.assertEqual(L.load_language(p),lang)
                self.assertEqual(json.loads(p.read_text())['other'],7)
    def test_corrupt_preferences_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ui.json'; p.write_text('broken')
            with self.assertRaises(ValueError): L.save_language('en',p)
            self.assertEqual(p.read_text(),'broken')
    def test_locale_fallback(self):
        with tempfile.TemporaryDirectory() as d, patch.object(L,'system_language',return_value='en'):
            self.assertEqual(L.load_language(Path(d)/'absent'),'en')
    def test_auto_device_compatible_both_directions(self):
        for lang in ('ko','en'):
            with patch.object(L,'LANGUAGE',lang):
                for value in (L.AUTO_KO,EN[L.AUTO_KO]):
                    self.assertEqual(L.display_device(value),L.tr(L.AUTO_KO))
                    self.assertEqual(L.canonical_device(value),L.AUTO_KO)
                self.assertEqual(L.display_device('Actual device name'),'Actual device name')
    def test_dynamic_status_translation(self):
        with patch.object(L,'LANGUAGE','en'):
            self.assertEqual(L.tr('게임 전용 PID 123'),'Game-only PID 123')
            self.assertEqual(L.tr('연결됨 · 기존 브리지 전송'),'Connected · Original bridge transport')
    def test_all_display_literals_covered(self):
        import ast
        tree=ast.parse(Path('app.py').read_text(encoding='utf-8-sig'))
        for n in ast.walk(tree):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='tr' and n.args and isinstance(n.args[0],ast.Constant):
                text=n.args[0].value
                if isinstance(text,str) and any('\uac00'<=c<='\ud7a3' for c in text): self.assertIn(text,EN)

if __name__=='__main__': unittest.main()
