import unittest,time
from unittest.mock import Mock
from battery import BatteryMonitor,battery_text,battery_cells
from studio_slots import StudioClient
from test_studio_slots import Fake,info
class BatteryTests(unittest.TestCase):
 def test_four_cell_boundaries_and_unknown(self):
  m=self.setup_monitor()
  self.assertIsNone(battery_cells(m))
  m.state='ready'
  for percent,cells in [(0,0),(1,1),(25,1),(26,2),(50,2),(51,3),(75,3),(76,4),(100,4)]:
   m.value={'percent':percent};self.assertEqual(battery_cells(m),cells)
  m.state='unavailable';self.assertIsNone(battery_cells(m))
 def test_decode_and_read_only(self):
  for raw,pct,state in [(0x08,80,0),(0x15,50,1),(0x2a,100,2),(0xf0,0,15)]:
   d=Fake([info(),bytes([0x81,0x66,4,0x68,raw])+bytes(59)])
   self.assertEqual(StudioClient(d,sleep=lambda _:None).battery(),dict(percent=pct,state=state,raw=raw))
   self.assertEqual([x[2] for x in d.sent],[10,4])
 def test_no_data_not_empty_battery(self):
  d=Fake([info(),bytes([0x81,0x66,4,0x68,0])+bytes(59)])
  self.assertIsNone(StudioClient(d,sleep=lambda _:None).battery())
 def test_bad_level(self):
  d=Fake([info(),bytes([0x81,0x66,4,0x68,0x0f])+bytes(59)])
  with self.assertRaises(RuntimeError):StudioClient(d,sleep=lambda _:None).battery()
 def setup_monitor(self):
  self.now=0;self.enum=Mock(return_value=[{'path':b'p'}]);self.read=Mock(return_value=dict(percent=80,state=0,raw=8))
  return BatteryMonitor(self.enum,self.read,clock=lambda:self.now,wall=lambda:1000)
 def finish(self,m):
  result=m.queue.get(timeout=2);m.queue.put(result);m.tick(paused=True)
 def test_five_minute_rate(self):
  m=self.setup_monitor();m.tick();self.finish(m)
  for t in range(1,300):self.now=t;m.tick()
  self.assertEqual(self.enum.call_count,1);self.assertEqual(self.read.call_count,1)
  self.now=300;m.tick();self.finish(m)
  self.assertEqual(self.enum.call_count,2);self.assertEqual(self.read.call_count,2)
 def test_minimized_and_manual(self):
  m=self.setup_monitor();m.tick(paused=True);self.enum.assert_not_called()
  m.tick();self.finish(m);m.refresh();self.now=1;m.tick();self.finish(m)
  self.assertEqual(self.read.call_count,2)
 def test_disconnect_reconnect_and_failure_clear(self):
  m=self.setup_monitor();m.tick();self.finish(m)
  self.enum.return_value=[];self.now=300;m.tick();self.finish(m)
  self.assertEqual(m.state,'disconnected');self.assertIsNone(m.value)
  self.enum.return_value=[{'path':b'p'}];self.now=600;m.tick();self.finish(m);self.assertEqual(m.state,'ready')
  self.read.side_effect=OSError();self.now=900;m.tick();self.finish(m);self.assertEqual(m.state,'unavailable');self.assertIsNone(m.value)
 def test_multiple_requires_selection(self):
  m=self.setup_monitor();self.enum.return_value=[{'path':b'p'},{'path':b'q'}]
  m.tick();self.finish(m);self.assertEqual(m.state,'multiple');self.read.assert_not_called()
  m.tick(preferred=b'q');self.finish(m);self.read.assert_called_once_with(b'q',action='read_battery')
 def test_labels(self):
  m=self.setup_monitor();m.tick();self.finish(m)
  self.assertIn('80%',battery_text(m,'ko'));self.assertIn('on battery',battery_text(m,'en'))
if __name__=='__main__':unittest.main()
