import hashlib
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from audio import OutputProcessor, original_namespace, ORIGINAL
from core import Controls

def route(ns, samples, rate, transform=None):
    chunks=[samples[i:i+480].astype('<i2').tobytes() for i in range(0,len(samples),480)]
    writes=[]; opens=[]
    class Stream:
        def read(self,n,**kw):
            assert n==480
            if not chunks: raise KeyboardInterrupt()
            return chunks.pop(0)
        def write(self,b,**kw): writes.append(transform(b) if transform else b)
        def close(self): pass
        def stop_stream(self): pass
    class PA:
        def get_device_info_by_index(self,i): return dict(name='fake',defaultSampleRate=rate,maxInputChannels=samples.shape[1])
        def open(self,**kw): opens.append(kw); return Stream()
        def terminate(self): pass
    saved=ns['pyaudio']
    ns['pyaudio']=SimpleNamespace(PyAudio=PA,paInt16=8)
    try:
        code=ns['run'](SimpleNamespace(list=False,in_index=1,out_index=2,map='duplicate',verbose=False))
        assert code==0
    finally: ns['pyaudio']=saved
    return b''.join(writes),opens

class CompatibilityTests(unittest.TestCase):
    def test_vendor_hash(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),'b5a76b746e952ecb736dd424f3306e93c962d5a67174b4b4cb2a17422ea2e390')
    def test_all_rates_channels_actual_legacy_loop(self):
        # runpy executes the preserved vendor source, not our AST loader.
        import runpy
        reference=ORIGINAL
        if not reference.exists(): reference=ORIGINAL
        self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(),'b5a76b746e952ecb736dd424f3306e93c962d5a67174b4b4cb2a17422ea2e390')
        old=runpy.run_path(str(reference),run_name='test_original')
        old['run'].__globals__['print']=lambda *a,**k:None
        # runpy's returned dict and function globals may be distinct.
        old=old['run'].__globals__
        reports=[]
        for rate in (44100,48000,96000):
            for channels in (1,2,6):
                with self.subTest(rate=rate,channels=channels):
                    x=np.random.default_rng(51).integers(-32768,32768,(9600,channels),dtype=np.int16)
                    expected,args=route(old,x,rate)
                    p=OutputProcessor()
                    actual,new_args=route(original_namespace(),x,rate,lambda b:p.process(b,Controls(bypass=True)))
                    self.assertEqual(expected,actual)
                    self.assertEqual(args,new_args)
                    self.assertTrue(all(a['format']==8 and a['frames_per_buffer']==480 for a in args))
                    reports.append(dict(rate=rate,channels=channels,bytes=len(actual),bit_exact=True,open_arguments_equal=True))
        Path('reports').mkdir(exist_ok=True)
        Path('reports/compatibility_0.2.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    def test_first_block_full_pcm_range_exact(self):
        x=np.tile(np.arange(-32768,32768,dtype=np.int32).astype('<i2')[:,None],(1,4)).tobytes()
        self.assertEqual(OutputProcessor().process(x,Controls(bypass=True)),x)
    def test_toggle_to_bypass_immediate(self):
        x=np.tile(np.full((480,1),7000,dtype='<i2'),(1,4)).tobytes()
        p=OutputProcessor()
        for _ in range(200): p.process(x,Controls())
        self.assertEqual(p.process(x,Controls(bypass=True)),x)
    def test_pure_does_not_bypass_policy(self):
        x=np.full((480,4),12000,dtype='<i2').tobytes()
        p=OutputProcessor()
        self.assertEqual(p.process(x,Controls(mode='pure',bypass=True)),bytes(len(x)))
        self.assertEqual(p.process(x,Controls(mode='normal',bypass=True)),x)
    def test_filtered_path_maps_all_four_channels(self):
        rng=np.random.default_rng(7)
        stereo=rng.integers(-15000,15000,(480,2),dtype=np.int16)
        data=np.tile(stereo,(1,2)).tobytes()
        out=np.frombuffer(OutputProcessor().process(data,Controls()),'<i2').reshape(-1,4)
        np.testing.assert_array_equal(out[:,:2],out[:,2:])
        self.assertNotEqual(out.tobytes(),data)

if __name__=='__main__': unittest.main(verbosity=2)
