import unittest,json,importlib.util
from pathlib import Path
import numpy as np
from channel_mix import ChannelMixer
from core import Controls
from presets import PresetStore
import test_presets

class CenterTests(unittest.TestCase):
    def test_center_mapping_slew_and_off(self):
        x=np.zeros((4800,6),dtype='<i2');x[:,2]=12000
        m=ChannelMixer();a=np.frombuffer(m.process(x.tobytes(),6,48000,center=True),'<i2').reshape(-1,6)
        np.testing.assert_array_equal(a[-1,:2],[8485,8485]);self.assertLess(a[0,0],20)
        m.process(x.tobytes(),6,48000,center=False)
        self.assertEqual(m.process(x.tobytes(),6,48000),x.tobytes())
    def test_front_unity_stereo_and_clipping(self):
        x=np.zeros((4800,6),dtype='<i2');x[:,:2]=30000
        y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,center=True),'<i2').reshape(-1,6)
        np.testing.assert_array_equal(y,x)
        x[:,2]=20000;y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,center=True),'<i2').reshape(-1,6)
        np.testing.assert_array_equal(y[-1,:2],[32767,32767])
        stereo=x[:,:2].copy().tobytes();self.assertEqual(ChannelMixer().process(stereo,2,48000,center=True),stereo)
    def test_off_exact_071(self):
        spec=importlib.util.spec_from_file_location('old','tests/fixtures/channel_mix_071.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        for policy in ('hard','soft'):
            a=old.ChannelMixer();b=ChannelMixer()
            rng=np.random.default_rng(80)
            for rear,lfe in [(True,True),(False,False),(True,False)]:
                x=rng.integers(-32768,32768,(4800,6),dtype=np.int16).tobytes()
                self.assertEqual(a.process(x,6,48000,rear,lfe,policy),b.process(x,6,48000,rear,lfe,policy,center=False))
    def test_center_chunk_invariance(self):
        x=np.random.default_rng(81).integers(-32768,32768,(4800,6),dtype=np.int16)
        for policy in ('hard','soft'):
            a=ChannelMixer().process(x.tobytes(),6,48000,True,True,policy,True)
            m=ChannelMixer();b=b''.join(m.process(z.tobytes(),6,48000,True,True,policy,True) for z in np.split(x,10))
            self.assertEqual(a,b)

class Migration(unittest.TestCase):
    setUp=test_presets.PresetTests.setUp
    def test_v3_backup_and_center(self):
        self.path.write_text(json.dumps(dict(version=3,slots=[self.value]+[None]*11)),encoding='utf-8');original=self.path.read_bytes()
        store=PresetStore(self.path)
        self.assertFalse(Controls(**store.slots[0]['controls']).center)
        self.value['controls']['center']=True;store.save(0,self.value)
        self.assertEqual(self.path.with_name('presets.v3.backup.json').read_bytes(),original)
        self.assertTrue(PresetStore(self.path).slots[0]['controls']['center'])
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['version'],4)

if __name__=='__main__':unittest.main()
