import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from session_settings import SessionStore
from process_list import rank
class SettingsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'last.json'
  self.doc=dict(version=1,sort='cpu',slot=4,details=True,settings=dict(name='Last settings',game_exe='game.exe',scope='process',channels=6,input='Automatic',output='DualSense',controls=dict(mode='normal',bypass=False,strength=.73,background=True,transient=False,rear=True,center=False,lfe=True,limiter='soft')))
 def test_roundtrip_no_pid(self):
  SessionStore(self.path).save(self.doc);self.assertEqual(SessionStore(self.path).value,self.doc);self.assertNotIn('pid',self.path.read_text())
 def test_corrupt_preserved(self):
  self.path.write_text('{broken');store=SessionStore(self.path)
  with self.assertRaises(ValueError):store.save(self.doc)
  self.assertEqual(self.path.read_text(),'{broken')
 def test_failed_replace_preserves(self):
  store=SessionStore(self.path);store.save(self.doc);before=self.path.read_bytes();changed=copy.deepcopy(self.doc);changed['sort']='name'
  with patch('session_settings.os.replace',side_effect=OSError('locked')):
   with self.assertRaises(OSError):store.save(changed)
  self.assertEqual(self.path.read_bytes(),before)
 def test_unchanged_skips_write(self):
  store=SessionStore(self.path);store.save(self.doc)
  with patch('session_settings.os.replace') as replace:store.save(self.doc);replace.assert_not_called()
 def test_invalid_rejected(self):
  for key,value in [('sort','gpu'),('slot',12),('details',1)]:
   doc=copy.deepcopy(self.doc);doc[key]=value
   with self.assertRaises(ValueError):SessionStore(self.path).save(doc)
class SortTests(unittest.TestCase):
 def test_cpu_order_normalized(self):
  rows=[('a',1),('b',2),('c',3)];r=rank(rows,{1:(1,0),2:(2,0),3:(3,0)},{1:(1,.1),2:(2,.8),3:(3,0)},1,4)
  self.assertEqual([x[1] for x in r],[2,1,3]);self.assertAlmostEqual(r[0][2],20)
 def test_unknown_last_and_pid_reuse(self):
  r=rank([('a',1),('b',2),('c',3)],{1:(1,0),2:(2,0)},{1:(100,20),2:(2,0)},1,4)
  self.assertEqual(r[0][1],2);self.assertIsNone(r[1][2]);self.assertIsNone(r[2][2])
 def test_tie_name_order(self):
  r=rank([('z',2),('A',1)],{1:(1,0),2:(2,0)},{1:(1,0),2:(2,0)},1,1)
  self.assertEqual([x[0] for x in r],['A','z'])
if __name__=='__main__':unittest.main()
