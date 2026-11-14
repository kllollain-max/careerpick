import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from validate import validate

class CardnewsSafetyTests(unittest.TestCase):
 def data(self):
  return {'verified':True,'source':'https://official.example.test/notice','cards':[{'title':'채용 안내','sections':[{'heading':'모집','items':['공고 원문 확인']}]} for _ in range(3)],'threads_caption':'채용 안내\n자세한 사항은 프로필링크 확인'}
 def test_unverified_rejected(self):
  d=self.data();d['verified']=False;self.assertTrue(validate(d))
 def test_demo_rejected(self):
  d=self.data();d['source']='DEMO ONLY';self.assertTrue(validate(d))
 def test_threads_url_rejected(self):
  d=self.data();d['threads_caption']='https://example.com\n자세한 사항은 프로필링크 확인';self.assertTrue(validate(d))
 def test_card_count_rejected(self):
  d=self.data();d['cards']=d['cards'][:2];self.assertTrue(validate(d))
 def test_invalid_data_no_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   src=Path(tmp)/'input.json';out=Path(tmp)/'out';d=self.data();d['verified']=False
   src.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
   p=subprocess.run([sys.executable,str(ROOT/'generate.py'),str(src),str(out)],capture_output=True,text=True)
   self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())

 def test_existing_output_preserved(self):
  with tempfile.TemporaryDirectory() as tmp:
   src=Path(tmp)/'input.json';out=Path(tmp)/'out';out.mkdir()
   sentinel=out/'keep.txt';sentinel.write_text('unchanged',encoding='utf-8')
   d=self.data();d['source']='https://example.org/official';d['verified']=True
   src.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
   p=subprocess.run([sys.executable,str(ROOT/'generate.py'),str(src),str(out)],capture_output=True,text=True)
   self.assertNotEqual(p.returncode,0)
   self.assertEqual(sentinel.read_text(encoding='utf-8'),'unchanged')
   self.assertEqual(sorted(x.name for x in out.iterdir()),['keep.txt'])

if __name__=='__main__':unittest.main()
