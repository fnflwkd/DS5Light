import unittest
from studio_slots import StudioClient,Slot
class Fake:
 def __init__(self,replies): self.replies=list(replies);self.sent=[]
 def send_feature_report(self,p):self.sent.append(p);return len(p)
 def get_feature_report(self,r,n):assert r in (0x81,0x84);return self.replies.pop(0) if self.replies else bytes(64)
def info(i=0,valid=1,name='Audio Haptics',status=0):
 return bytes([0x84,0x66,0x0a,status,i,valid,19])+name.encode()[:16].ljust(16,b'\0')+bytes(41)
def activate(status=0,reconnect=0):return bytes([0x84,0x66,9,status,0,reconnect,0])+bytes(57)
class Tests(unittest.TestCase):
 def client(self,replies):
  d=Fake(replies);return StudioClient(d,sleep=lambda _:None),d
 def test_names_and_empty(self):
  c,d=self.client([info(name='테스트'),info(1,0)])
  self.assertEqual(c.info(0).name,'테스트');self.assertEqual(c.info(1).label(),'02 · Empty')
  self.assertTrue(all(x[2]==10 for x in d.sent))
 def test_unavailable_not_empty(self):
  c,d=self.client([info(status=1)]);self.assertEqual(c.info(0).state,'unavailable')
 def test_stale_and_pending(self):
  c,d=self.client([info(1),info(status=254),info()]);self.assertEqual(c.info(0).name,'Audio Haptics')
 def test_timeout_not_empty(self):
  c,d=self.client([])
  with self.assertRaises(TimeoutError):c.info(0)
 def test_empty_cannot_activate(self):
  c,d=self.client([info(valid=0)])
  with self.assertRaises(ValueError):c.activate(0)
  self.assertEqual([p[2] for p in d.sent],[10])
 def test_deferred_and_reconnect(self):
  c,d=self.client([info(),activate(2,1)]);r=c.activate(0)
  self.assertTrue(r['deferred']);self.assertTrue(r['reconnect']);self.assertEqual([p[2] for p in d.sent],[10,9])
 def test_activation_not_retried(self):
  c,d=self.client([info()])
  with self.assertRaises(TimeoutError):c.activate(0)
  self.assertEqual([p[2] for p in d.sent],[10,9])
 def test_bounds_and_write_whitelist(self):
  c,d=self.client([])
  for cmd,idx in [(8,0),(3,0),(9,10),(10,-1)]:
   with self.assertRaises(ValueError):c.request(cmd,idx)
  self.assertFalse(d.sent)
 def test_ten_slots(self):
  c,d=self.client([info(i,valid=i%2) for i in range(10)])
  self.assertEqual(len(c.slots()),10);self.assertEqual([p[3] for p in d.sent],list(range(10)))
 def test_rejection(self):
  c,d=self.client([info(),activate(1)])
  with self.assertRaises(RuntimeError):c.activate(0)


def strength(value=100,field=0x13):return bytes([0x81,0x66,4,field,value])+bytes(59)
def ack(status=0):return bytes([0x81,0x66,1,status])+bytes(60)
class IntensityTests(unittest.TestCase):
 def client(self,replies):
  d=Fake(replies);return StudioClient(d,sleep=lambda _:None),d
 def test_read_limits(self):
  for value in (0,100,200):
   c,d=self.client([strength(value)]);self.assertEqual(c.intensity(),value)
   self.assertEqual(d.sent[0][:4],bytes([0x80,0x66,4,0x13]))
 def test_write_and_verify_only_intensity(self):
  c,d=self.client([strength(),ack(),strength(150)])
  self.assertEqual(c.set_intensity(150),150)
  self.assertEqual([p[:5] for p in d.sent],[bytes([0x80,0x66,4,0x13,0]),bytes([0x80,0x66,1,0x13,150]),bytes([0x80,0x66,4,0x13,0])])
 def test_invalid_no_io(self):
  c,d=self.client([])
  for value in (-1,201,1.5,True,None):
   with self.assertRaises(ValueError):c.set_intensity(value)
  self.assertFalse(d.sent)
 def test_stale(self):
  c,d=self.client([info(),strength(88,0x12),strength(125)]);self.assertEqual(c.intensity(),125)
 def test_missing_prevents_write(self):
  c,d=self.client([])
  with self.assertRaises(TimeoutError):c.set_intensity(150)
  self.assertEqual([p[2] for p in d.sent],[4])
 def test_mismatch(self):
  c,d=self.client([strength(),ack(),strength()])
  with self.assertRaises(RuntimeError):c.set_intensity(150)
 def test_rejected(self):
  c,d=self.client([strength(),ack(1)])
  with self.assertRaises(RuntimeError):c.set_intensity(150)
 def test_timeout_not_retried(self):
  c,d=self.client([strength()])
  with self.assertRaises(TimeoutError):c.set_intensity(150)
  self.assertEqual([p[2] for p in d.sent],[4,1])
 def test_disconnect(self):
  c,d=self.client([])
  def unplug(*args):raise OSError('unplugged')
  d.get_feature_report=unplug
  with self.assertRaises(TimeoutError):c.set_intensity(150)
  self.assertEqual([p[2] for p in d.sent],[4])


class ExtraControlTests(unittest.TestCase):
 def reply(self,field,value):
  import struct
  data=struct.pack('<f',value) if field==1 else bytes([value])
  return bytes([0x81,0x66,4,field])+data+bytes(60-len(data))
 def test_gain_float_and_verified_write(self):
  import struct
  d=Fake([self.reply(1,1.3),ack(),self.reply(1,1.5)])
  self.assertAlmostEqual(StudioClient(d,sleep=lambda _:None).control(1,1.5),1.5)
  self.assertEqual(d.sent[1][:8],bytes([0x80,0x66,1,1])+struct.pack('<f',1.5))
 def test_trigger_common_field(self):
  d=Fake([self.reply(0xc0,0),ack(),self.reply(0xc0,4)])
  self.assertEqual(StudioClient(d,sleep=lambda _:None).control(0xc0,4),4)
  self.assertEqual(d.sent[1][:5],bytes([0x80,0x66,1,0xc0,4]))
  self.assertEqual([p[2] for p in d.sent],[4,1,4])
 def test_invalid_no_writes(self):
  d=Fake([]);c=StudioClient(d,sleep=lambda _:None)
  for field,value in [(1,0),(1,2.1),(1,float('nan')),(1,True),(0xc0,11),(0xc0,1.5),(0x2c,50)]:
   with self.assertRaises(ValueError):c.control(field,value)
  self.assertFalse(d.sent)
 def test_unsupported_gain(self):
  d=Fake([self.reply(1,0)])
  with self.assertRaises(RuntimeError):StudioClient(d,sleep=lambda _:None).control(1,1.2)
  self.assertEqual(len(d.sent),1)
 def test_trigger_rejection(self):
  d=Fake([self.reply(0xc0,0),ack(1)])
  with self.assertRaises(RuntimeError):StudioClient(d,sleep=lambda _:None).control(0xc0,5)
  self.assertEqual(len(d.sent),2)
 def test_mismatch(self):
  d=Fake([self.reply(0xc0,0),ack(),self.reply(0xc0,0)])
  with self.assertRaises(RuntimeError):StudioClient(d,sleep=lambda _:None).control(0xc0,5)


class ProfileTests(unittest.TestCase):
 def reply(self,index=3,edited=1,status=0):return bytes([0x81,0x66,0x67,status,index,edited])+b'Audio Haptics'.ljust(16,b'\0')+bytes(42)
 def test_current_slot_read_only(self):
  d=Fake([self.reply()]);r=StudioClient(d,sleep=lambda _:None).profile()
  self.assertEqual(r,dict(index=3,edited=True,name='Audio Haptics'));self.assertEqual(d.sent,[bytes([0x80,0x66,0x67])+bytes(61)])
 def test_unknown_not_first_slot(self):
  d=Fake([self.reply(255)]);self.assertIsNone(StudioClient(d,sleep=lambda _:None).profile()['index'])
 def test_stale_reply_ignored(self):
  d=Fake([info(),self.reply()]);self.assertEqual(StudioClient(d,sleep=lambda _:None).profile()['index'],3)
 def test_bad_response(self):
  d=Fake([self.reply(edited=2)])
  with self.assertRaises(RuntimeError):StudioClient(d,sleep=lambda _:None).profile()
 def test_unsupported(self):
  d=Fake([])
  with self.assertRaises(TimeoutError):StudioClient(d,sleep=lambda _:None).profile()
if __name__=='__main__':unittest.main()
