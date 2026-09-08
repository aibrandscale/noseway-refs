import importlib.util,json,tempfile,unittest,datetime as dt
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('pipeline',Path(__file__).parents[1]/'scripts/pipeline.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class PipelineTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.patch=patch.object(p,'ROOT',self.root);self.patch.start()
  self.s={'title':'Test','prompt':'One pouch. EXACT AD TEXT: "'+p.OFFER+'"','copy':p.OFFER+'\nПоръчай сега.\n'+p.PDP,'framework':'AIDA'}
  self.old={'key':'cr-39','kind':'creative','name':'39 Test','link':p.RAW+'/creatives-2026-09-07/39.jpg','copy':'old'}
  p.write('sheet.json',{'rows':[self.old]})
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def test_48_hours_without_month_boundary_bug(self):
  for days in [0,1,2,22,23,24,50]:
   t=p.ANCHOR+dt.timedelta(days=days)
   self.assertEqual(p.batch_id(t),'batch-'+str(days//2+1).zfill(4))
 def test_batch_exactly_ten_idempotent(self):
  specs=[dict(self.s,prompt=self.s['prompt']+str(i)) for i in range(10)]
  with patch.object(p,'now',return_value=p.ANCHOR):
   self.assertEqual(p.enqueue_batch(specs)['created'],10)
   self.assertEqual(p.enqueue_batch(specs)['created'],0)
  self.assertEqual(len(list((self.root/'jobs/requests').glob('*.json'))),10)
 def test_batch_invalid_is_atomic(self):
  specs=[dict(self.s,prompt=str(i)) for i in range(10)];specs[-1]['copy']='invalid'
  with patch.object(p,'now',return_value=p.ANCHOR),self.assertRaises(ValueError):p.enqueue_batch(specs)
  self.assertFalse((self.root/'jobs/requests').exists())
 def rework(self):return p.enqueue_rework(dict(self.s,key='cr-39',base_link=self.old['link'],feedback='Correct lettering'))['id']
 def test_rework_dedup_and_reference_order(self):
  rid=self.rework();self.assertEqual(rid,self.rework());req=p.read('jobs/requests/'+rid+'.json')
  body=p.payload(req);self.assertEqual(body['input']['image_input'],[p.PACK,p.STRIP,self.old['link']])
  self.assertNotIn('image_urls',body['input']);self.assertIn(p.OFFER,body['input']['prompt'])
 def test_cannot_publish_without_qa(self):
  rid=self.rework();p.write('jobs/results/'+rid+'.json',{'attempt':1,'link':'new'})
  with self.assertRaises(ValueError):p.publish(rid)
  self.assertEqual(p.read('sheet.json')['rows'][0]['link'],self.old['link'])
 def test_qa_is_versioned_and_requires_all_checks(self):
  rid=self.rework();link=p.RAW+'/creatives-2026-09-09/new.jpg'
  p.write('jobs/results/'+rid+'.json',{'attempt':1,'link':link,'status':'generated'})
  q={'id':rid,'attempt':1,'link':link,'decision':'accept','feedback':'Inspected'}
  with self.assertRaises(ValueError):p.review(q)
  q['checks']={k:True for k in ['packaging','logo','one_pack','bulgarian_text','offer','feedback_applied']};p.review(q)
  self.assertTrue(p.publish(rid)['published']);self.assertFalse(p.publish(rid)['published'])
  self.assertEqual(len(p.read('sheet.json')['rows']),1)
 def test_changed_original_rejects_stale_rework(self):
  rid=self.rework();p.write('jobs/results/'+rid+'.json',{'attempt':1,'link':'new'})
  p.write('jobs/reviews/'+rid+'.json',{'attempt':1,'link':'new','decision':'accept'})
  p.write('sheet.json',{'rows':[dict(self.old,copy='user changed copy')]})
  with self.assertRaises(ValueError):p.publish(rid)
if __name__=='__main__':unittest.main()
