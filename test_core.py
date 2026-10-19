import unittest
import numpy as np
from core import *
from offline import process_array

class CoreTests(unittest.TestCase):
    def test_bypass_reconstructs_and_duplicate(self):
        rng=np.random.default_rng(20)
        x=rng.uniform(-.2,.2,(48000,6)).astype(np.float32)
        y,_=process_array(x,controls=Controls(bypass=True))
        np.testing.assert_allclose(y[240:,:2],x[240:,:2],atol=2e-7)
        np.testing.assert_array_equal(y[:,:2],y[:,2:])
    def test_silence_and_tiny(self):
        for level in (0,1e-12):
            y,_=process_array(np.full((9600,2),level))
            self.assertTrue(np.isfinite(y).all())
            self.assertLessEqual(np.max(abs(y)),level+1e-10)
    def test_antiphase(self):
        x=np.sin(np.arange(48000)*2*np.pi*80/RATE)*.1
        a,_=process_array(np.column_stack((x,x)))
        b,_=process_array(np.column_stack((x,-x)))
        np.testing.assert_allclose(a[:,0],b[:,0],atol=1e-7)
        np.testing.assert_allclose(b[:,0],-b[:,1],atol=1e-7)
    def test_pure_fails_closed_even_bypass(self):
        p=Processor(); c=Controls(mode='pure',bypass=True)
        x=np.full((BLOCK,2),.2)
        self.assertEqual(np.max(abs(p.process(x,c,now=1))),0)
        r=RumbleSample(1,.5,0,True)
        self.assertGreater(np.max(p.process(x,c,r,now=1)),.19)
        p.process(x,c,r,now=1.2)
        self.assertEqual(np.max(abs(p.process(x,c,r,now=1.205))),0)
        self.assertEqual(np.max(abs(p.process(x,c,RumbleSample(5,.9,0,True),now=1.3))),0)
    def test_mock_and_mode_transition(self):
        provider=MockRumbleProvider(); provider.value=RumbleSample(.1,1,0,True)
        p=Processor(); x=np.ones((BLOCK,2))*.1
        p.process(x,Controls(bypass=True),now=0)
        y=p.process(x,Controls(mode='pure',bypass=True),provider.sample(),now=.1)
        self.assertGreater(y[-1,0],.09)
        p.process(x,Controls(mode='pure',bypass=True),now=.2)
        self.assertEqual(p.process(x,Controls(mode='pure',bypass=True),now=.3).max(),0)
    def test_resampling_chunk_invariance(self):
        for rate in (44100,96000):
            x=np.random.default_rng(5).normal(0,.1,(rate,2))
            a=StreamingResampler(rate).process(x)
            r=StreamingResampler(rate)
            b=np.concatenate([r.process(x[i:i+211]) for i in range(0,len(x),211)])
            self.assertLess(abs(len(a)-len(b)),2)
            np.testing.assert_allclose(a[:min(len(a),len(b))],b[:min(len(a),len(b))],atol=1e-6)
    def test_resampler_alias_rejection(self):
        rate=96000; t=np.arange(rate)/rate
        x=np.sin(2*np.pi*35000*t)
        y=StreamingResampler(rate).process(np.column_stack((x,x)))
        self.assertLess(np.sqrt(np.mean(y[1000:]**2)),.025)
    def test_ring_bounded_and_silent_underrun(self):
        r=FrameRing(); r.push(np.ones((1000,2)))
        self.assertGreater(r.pop(240).max(),.9)
        for _ in range(10): r.pop(240)
        self.assertEqual(r.pop(240).max(),0)
        for _ in range(50): r.push(np.ones((240,2)))
        self.assertLessEqual(r.count,r.capacity); self.assertGreater(r.drops,0)
    def test_invalid_audio(self):
        with self.assertRaises(ValueError): Processor().process(np.full((240,2),np.nan))
    def test_module_switches(self):
        t=np.arange(96000)/RATE; x=np.column_stack((.1*np.sin(2*np.pi*60*t),.1*np.sin(2*np.pi*60*t)))
        a,_=process_array(x); b,_=process_array(x,controls=Controls(background=False))
        self.assertLess(np.std(a[-24000:]),np.std(b[-24000:])*.7)
    def test_drift_long_simulation(self):
        r=FrameRing(); r.push(np.ones((960,2))*.1)
        for i in range(24000): # 120 seconds with +500ppm source clock
            r.push(np.ones((241 if i%8==0 else 240,2))*.1)
            r.pop(240)
        self.assertEqual(r.drops,0); self.assertEqual(r.underruns,0)
        self.assertLess(r.count,2400)

if __name__=='__main__': unittest.main(verbosity=2)
