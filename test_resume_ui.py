import sys,time,tempfile,unittest,tkinter as tk
from pathlib import Path
from unittest.mock import patch
import app
class ResumeUITests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.args=patch.object(sys,'argv',['app','--preset-test-path',str(Path(self.temp.name)/'presets.json')]);self.args.start();self.addCleanup(self.args.stop)
  self.devices=patch('app.devices',return_value=[]);self.devices.start();self.addCleanup(self.devices.stop)
  self.processes=patch('app.process_list',return_value=[('game.exe',233,10.),('other.exe',234,0.)]);self.process_rows=self.processes.start();self.addCleanup(self.processes.stop)
  self.battery=patch('app.BatteryMonitor.tick');self.battery.start();self.addCleanup(self.battery.stop)
  self.open()
 def open(self):self.root=tk.Tk();self.a=app.App(self.root)
 def destroy(self):
  for timer in self.root.tk.call('after','info'):self.root.after_cancel(timer)
  self.root.destroy()
 def tearDown(self):self.destroy()
 def pump(self,seconds=.4):
  end=time.monotonic()+seconds
  while time.monotonic()<end:self.root.update();time.sleep(.01)
 def test_restore_options_without_start(self):
  a=self.a;self.pump();a.scope.set('process');a.channel.set(next(k for k,v in app.CHANNELS.items() if v==2));a.strength.set(73);a.center.set(False);a.rear.set(False);a.lfe.set(True);a.filter_on.set(False)
  a.process_order.set(next(k for k,v in app.PROCESS_SORT.items() if v=='cpu'));a.slot.current(4);a.slot_selected();a.toggle_details()
  a.game.set(next(k for k,v in a.game_map.items() if v==233));a.game_selected();self.pump(1)
  self.assertIsNotNone(a.session.value);self.assertFalse(a.store.path.exists())
  self.destroy();self.open();a=self.a;self.pump()
  self.assertEqual(a.scope.get(),'process');self.assertEqual(app.CHANNELS[a.channel.get()],2);self.assertEqual(a.strength.get(),73)
  self.assertFalse(a.center.get());self.assertFalse(a.rear.get());self.assertTrue(a.lfe.get());self.assertFalse(a.filter_on.get());self.assertTrue(a.advanced_open)
  self.assertEqual(a.slot.current(),4);self.assertEqual(a.game_map.get(a.game.get()),233);self.assertEqual(app.PROCESS_SORT[a.process_order.get()],'cpu');self.assertIsNone(a.engine)
 def test_refresh_keeps_selected_process(self):
  self.pump();a=self.a;a.scope.set('process');a.game.set(next(k for k,v in a.game_map.items() if v==233));a.game_selected()
  self.process_rows.return_value=[('other.exe',234,20.),('game.exe',233,2.)]
  a.process_order.set(next(k for k,v in app.PROCESS_SORT.items() if v=='cpu'));a.refresh_games();self.pump()
  self.assertEqual(a.game_map.get(a.game.get()),233);self.assertTrue(list(a.game_map)[0].startswith('other.exe'));self.assertIsNone(a.engine)
 def test_refresh_failure_clears_stale_pid(self):
  self.pump();a=self.a;a.game.set(next(k for k,v in a.game_map.items() if v==233));a.game_selected()
  self.process_rows.side_effect=OSError('failed');a.refresh_games();self.pump()
  self.assertEqual(a.game.get(),'');self.assertEqual(a.game_map,{});self.assertEqual(a.desired_game,'game.exe')
 def test_pc_preset_does_not_write_or_restore_studio(self):
  self.pump();a=self.a;p=a.studio_window
  with patch('studio_ui.run_device') as device:
   p.extra['gain']['value'].set(1.3);a.slot_name.set('PC only');a.save_slot()
   p.extra['gain']['value'].set(1.7);p.intensity_value.set(80);p.extra['trigger']['value'].set(4)
   a.load_slot();self.pump()
   self.assertEqual(p.extra['gain']['value'].get(),1.7)
   self.assertEqual(p.intensity_value.get(),80);self.assertEqual(p.extra['trigger']['value'].get(),4)
   device.assert_not_called()
 def test_embedded_panel_and_static_battery(self):
  a=self.a;self.pump();self.assertTrue(a.studio_window.embedded)
  self.assertFalse(any(isinstance(w,tk.Toplevel) for w in self.root.winfo_children()))
  m=a.battery;m.state='ready';m.value={'percent':70,'state':0}
  a.battery_icon.show(m);items=a.battery_icon.find_all()
  for _ in range(10):a.battery_icon.show(m)
  self.assertEqual(a.battery_icon.find_all(),items)
  self.assertEqual(a.battery_icon.previous,3)
if __name__=='__main__':unittest.main()
