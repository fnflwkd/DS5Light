import json
import unittest
from unittest.mock import patch
import numpy as np
from channel_mix import ChannelMixer
from core import Controls
from audio import Engine, OutputProcessor, original_namespace
import test_presets


class MixTests(unittest.TestCase):
    def test_disabled_exact_and_stereo_unchanged(self):
        for ch in (1,2,6,8):
            x=np.random.default_rng(ch).integers(-32768,32768,(960,ch),dtype=np.int16).tobytes()
            self.assertEqual(ChannelMixer().process(x,ch,48000),x)
            if ch!=6: self.assertEqual(ChannelMixer().process(x,ch,48000,True,True),x)

    def test_channels_and_center_exclusion(self):
        for rear,lfe in ((False,False),(True,False),(False,True),(True,True)):
            for channel in range(6):
                x=np.zeros((2000,6),dtype='<i2'); x[:,channel]=14000
                y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,rear,lfe),'<i2').reshape(-1,6)
                r=.5*rear; f=.25*lfe
                expected=np.rint(14000*np.array([float(channel==0)+r*(channel==4)+f*(channel==3),
                                                 float(channel==1)+r*(channel==5)+f*(channel==3)]))
                np.testing.assert_array_equal(y[-1,:2],expected)

    def test_slew_and_chunk_invariance_and_return_exact(self):
        x=np.zeros((2880,6),dtype='<i2'); x[:,4:]=24000
        a=ChannelMixer().process(x.tobytes(),6,48000,True,True)
        m=ChannelMixer()
        b=b''.join(m.process(chunk.tobytes(),6,48000,True,True) for chunk in np.split(x,6))
        self.assertEqual(a,b)
        y=np.frombuffer(a,'<i2').reshape(-1,6)[:,:2]
        self.assertLess(np.max(np.abs(np.diff(y.astype(int),axis=0))),20)
        m.process(x.tobytes(),6,48000,False,False)
        self.assertEqual(m.process(x.tobytes(),6,48000),x.tobytes())

    def test_full_scale_no_overflow(self):
        for value in (-32768,32767):
            x=np.full((2000,6),value,dtype='<i2')
            y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,True,True),'<i2').reshape(-1,6)
            np.testing.assert_array_equal(x,y)

    def test_front_only_unity_with_both_switches(self):
        for limiter in ('hard','soft'):
            x=np.zeros((4800,6),dtype='<i2')
            x[:,:2]=np.random.default_rng(23).integers(-32768,32768,(4800,2),dtype=np.int16)
            y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,True,True,limiter),'<i2').reshape(-1,6)
            np.testing.assert_array_equal(y[:,:2],x[:,:2])

    def test_hard_clips_only_excess(self):
        x=np.zeros((4800,6),dtype='<i2'); x[:,0]=30000; x[:,4]=20000; x[:,1]=10000
        y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,True,False,'hard'),'<i2').reshape(-1,6)
        self.assertEqual(y[-1,0],32767)
        np.testing.assert_array_equal(y[:,1],x[:,1])

    def test_soft_links_stereo_and_recovers(self):
        m=ChannelMixer(); m.rear=.5
        x=np.zeros((4800,6),dtype='<i2'); x[:,0]=5000; x[:,1]=10000
        x[0,0]=30000; x[0,4]=20000
        y=np.frombuffer(m.process(x.tobytes(),6,48000,True,False,'soft'),'<i2').reshape(-1,6)
        self.assertEqual(y[0,0],32767)
        self.assertAlmostEqual(y[0,1]/10000,32767/40000,places=4)
        self.assertLess(y[1,0],5000)
        self.assertTrue(np.all(np.diff(y[1:,0].astype(int))>=0))
        np.testing.assert_array_equal(y[-1,:2],x[-1,:2])
        self.assertEqual(m.gain,1.)

    def test_mode_transition_bounded_and_settles(self):
        m=ChannelMixer(); m.rear=.5
        x=np.zeros((1920,6),dtype='<i2'); x[:,0]=30000; x[:,4]=20000; x[:,1]=10000
        m.process(x.tobytes(),6,48000,True,False,'hard')
        y=np.frombuffer(m.process(x.tobytes(),6,48000,True,False,'soft'),'<i2').reshape(-1,6)
        self.assertLess(np.max(np.abs(np.diff(y[:,1].astype(int)))),5)
        self.assertEqual(m.soft_mix,1.)
        m.process(x.tobytes(),6,48000,True,False,'hard')
        self.assertEqual(m.soft_mix,0.)

    def test_legacy_engine_reads_mix_before_channel_extraction(self):
        x=np.zeros((1920,6),dtype='<i2'); x[:,2]=30000; x[:,3]=4000; x[:,4]=12000; x[:,5]=-8000
        chunks=[a.tobytes() for a in np.split(x,4)]; writes=[]
        class Stream:
            def get_read_available(self): return 480
            def read(self,n,**kw):
                if not chunks: raise KeyboardInterrupt()
                return chunks.pop(0)
            def write(self,data,**kw): writes.append(data)
            def get_input_latency(self): return 0
            def get_output_latency(self): return 0
            def stop_stream(self): pass
            def close(self): pass
        class PA:
            def get_device_info_by_index(self,i): return dict(name='fake',defaultSampleRate=48000,maxInputChannels=6)
            def open(self,**kw): return Stream()
            def terminate(self): pass
        def namespace(module):
            ns=original_namespace(module); run=ns['run']
            def explicit(args):
                args.in_index=1; args.out_index=2
                return run(args)
            ns['run']=explicit
            return ns
        engine=Engine(controls=Controls(bypass=True,rear=True,lfe=True))
        with patch('audio.pa.PyAudio',PA),patch('audio.devices',return_value=[]),patch('audio.original_namespace',side_effect=namespace):
            engine._run()
        self.assertEqual(engine.errors,0)
        actual=np.frombuffer(b''.join(writes),'<i2').reshape(-1,4)
        expected=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,True,True),'<i2').reshape(-1,6)[:,:2]
        np.testing.assert_array_equal(actual,np.tile(expected,(1,2)))
        self.assertEqual(OutputProcessor().process(actual.tobytes(),Controls(mode='pure',bypass=True,rear=True,lfe=True)),bytes(actual.nbytes))


class MigrationTests(unittest.TestCase):
    setUp = test_presets.PresetTests.setUp
    def test_v1_backup_and_new_switches(self):
        self.path.write_text(json.dumps(dict(version=1,slots=[self.value]+[None]*11)),encoding='utf-8')
        original=self.path.read_bytes()
        from presets import PresetStore
        store=PresetStore(self.path)
        self.assertIsNone(store.error)
        self.value['controls'].update(rear=True,lfe=True)
        store.save(0,self.value)
        self.assertEqual(self.path.with_name('presets.v1.backup.json').read_bytes(),original)
        self.assertEqual(PresetStore(self.path).slots[0],self.value)


if __name__=='__main__': unittest.main()
