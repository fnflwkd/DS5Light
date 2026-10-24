import time,unittest,tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch
from studio_ui import StudioWindow
from studio_slots import Slot
class StudioUITests(unittest.TestCase):
 def setUp(self):
  self.values={'intensity':100,'gain':1.3,'trigger':0,'profile':dict(index=0,name='Audio',edited=False)};self.calls=[];self.fail=None;self.reconnect=False
  self.slots=[Slot(0,'saved','Audio'),Slot(1,'empty')]
  def run(path,index=None,action=None,value=None):
   self.calls.append((index,action,value))
   if action:
    key=action.split('_',1)[1]
    if key==self.fail:raise OSError('disconnected')
    if action.startswith('set_'):self.values[key]=value
    return self.values[key]
   if index is not None:return dict(slot=Slot(index,'saved','Audio'),reconnect=self.reconnect,deferred=False)
   return self.slots
  self.dp=patch('studio_ui.devices',return_value=[{'path':b'mock'}]);self.dp.start();self.addCleanup(self.dp.stop)
  self.rp=patch('studio_ui.run_device',side_effect=run);self.rp.start();self.addCleanup(self.rp.stop)
  self.root=tk.Tk();self.root.withdraw();self.app=SimpleNamespace(root=self.root,engine=None);self.p=StudioWindow(self.app)
 def tearDown(self):
  self.pump(.4)
  self.p.close();self.root.destroy()
 def pump(self,seconds=.55):
  until=time.monotonic()+seconds
  while time.monotonic()<until:self.root.update();time.sleep(.01)
 def writes(self):return [c for c in self.calls if c[1] and c[1].startswith('set_')]
 def test_auto_read_without_writes_or_idle_poll(self):
  self.pump();p=self.p
  self.assertTrue(p.intensity_known);self.assertTrue(all(e['known'] for e in p.extra.values()));self.assertFalse(self.writes())
  count=len(self.calls);self.pump();self.assertEqual(len(self.calls),count);self.assertIsNone(p.poll_id)
  self.assertFalse(p.intensity_read.winfo_manager());self.assertFalse(p.intensity_apply.winfo_manager())
 def test_drag_release_one_write(self):
  self.pump();p=self.p
  for value in range(101,151):p.intensity_value.set(value)
  self.assertFalse(self.writes());p.schedule_strength('intensity');self.pump()
  self.assertEqual(self.writes(),[(None,'set_intensity',150)])
  p.schedule_strength('intensity');self.pump();self.assertEqual(len(self.writes()),1)
 def test_keyboard_coalesces(self):
  self.pump();p=self.p
  for value in (1.4,1.5,1.6):p.extra['gain']['value'].set(value);p.schedule_strength('gain',100)
  self.pump();self.assertEqual(self.writes(),[(None,'set_gain',1.6)])
 def test_trigger_release(self):
  self.pump();p=self.p;p.extra['trigger']['value'].set(4.2);p.schedule_strength('trigger');self.pump()
  self.assertEqual(self.writes(),[(None,'set_trigger',4)])
 def test_gain_percent_and_maximum(self):
  self.pump();p=self.p
  self.assertEqual(p.strength_order,['gain','intensity','trigger'])
  self.assertEqual(p.extra['gain']['number'].cget('text'),'130%')
  self.assertEqual(float(p.extra['gain']['scale']['to']),2)
  p.extra['gain']['value'].set(2);p.schedule_strength('gain');self.pump()
  self.assertEqual(self.writes(),[(None,'set_gain',2)])
  self.assertEqual(p.extra['gain']['number'].cget('text'),'200%')
 def test_partial_read_failure(self):
  self.fail='trigger';self.pump();p=self.p
  self.assertTrue(p.intensity_known);self.assertTrue(p.extra['gain']['known']);self.assertFalse(p.extra['trigger']['known'])
  self.assertEqual(str(p.extra['trigger']['scale']['state']),'disabled');self.assertFalse(self.writes())
 def test_write_failure_disables(self):
  self.pump();p=self.p;self.fail='intensity';p.intensity_value.set(120);p.schedule_strength('intensity');self.pump()
  self.assertFalse(p.connected);self.assertEqual(str(p.intensity_scale['state']),'disabled')
 def test_slot_apply_restores_strength_controls(self):
  self.pump();p=self.p;p.choice.current(0);p.activate();self.pump()
  self.assertTrue(p.intensity_known);self.assertTrue(p.connected);self.assertFalse(self.writes())
  self.assertEqual(sum(index==0 and action is None for index,action,_ in self.calls),1)
 def test_slot_reconnect_required_no_auto_write(self):
  self.pump();self.reconnect=True;self.p.activate();self.pump()
  self.assertFalse(self.p.connected);self.assertFalse(self.writes())
 def test_empty_and_running_guards(self):
  self.pump();p=self.p;p.choice.current(1);p.selection();self.assertEqual(str(p.apply['state']),'disabled')
  p.choice.current(0);self.app.engine=object();count=len(self.calls);p.activate();self.assertEqual(len(self.calls),count)
 def test_dialog_fits(self):
  self.root.update();self.assertLessEqual(self.p.win.winfo_reqheight(),self.p.win.winfo_height())
 def test_current_fourth_slot_selected(self):
  self.slots=[Slot(i,'saved',f'Slot {i+1}') for i in range(10)]
  self.values['profile']=dict(index=3,name='Audio Haptics',edited=True);self.pump()
  self.assertEqual(self.p.choice.current(),3);self.assertIn('Audio Haptics',self.p.loaded_label.cget('text'));self.assertFalse(self.writes())
 def test_unknown_profile_no_first_slot(self):
  self.values['profile']=dict(index=None,name='',edited=False);self.pump()
  self.assertEqual(self.p.choice.current(),-1);self.assertTrue(self.p.intensity_known)
 def test_unsupported_profile_preserves_strengths(self):
  self.fail='profile';self.pump();self.assertEqual(self.p.choice.current(),-1);self.assertTrue(self.p.intensity_known)
 def test_outside_list_not_first_slot(self):
  self.values['profile']=dict(index=15,name='Other',edited=False);self.pump()
  self.assertEqual(self.p.choice.current(),-1);self.assertIn('16',self.p.loaded_label.cget('text'))
if __name__=='__main__':unittest.main()
