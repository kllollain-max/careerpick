import json,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).parent
class CardnewsRegression(unittest.TestCase):
 def setUp(self):
  self.d={'verified':False,'source':'DEMO ONLY','cards':[{'title':'채용 안내','sections':[{'heading':'모집','items':['공고 원문 확인']}]} for _ in range(5)],'threads_caption':'채용 안내\n자세한 사항은 프로필링크 확인'}
 def run_generator(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);source=p/'in.json';out=p/'out';source.write_text(json.dumps(self.d,ensure_ascii=False),encoding='utf-8')
   proc=subprocess.run([sys.executable,str(ROOT/'generate.py'),str(source),str(out)],capture_output=True,text=True)
   dims=[];zipok=False
   if out.exists():
    for x in out.glob('card_*.png'):
     with Image.open(x) as im:dims.append(im.size)
    if (out/'cardnews.zip').exists():
     with zipfile.ZipFile(out/'cardnews.zip') as z:zipok=z.testzip() is None
   return proc.returncode,out.exists(),dims,zipok
 def test_demo_rejected(self):
  rc,exists,*_=self.run_generator();self.assertNotEqual(rc,0);self.assertFalse(exists)
 def test_five_cards(self):
  self.d.update(source='https://example.org/official-notice',verified=True)
  rc,exists,dims,zipok=self.run_generator();self.assertEqual(rc,0);self.assertTrue(exists);self.assertEqual(len(dims),5);self.assertTrue(all(x==(1080,1350) for x in dims));self.assertTrue(zipok)
 def test_overflow_rejected(self):
  self.d.update(source='https://example.org/official-notice',verified=True)
  self.d['cards'][4]['sections'][0]['items']=['긴 문장'*1000]
  rc,exists,*_=self.run_generator();self.assertNotEqual(rc,0);self.assertFalse(exists)
 def test_url_rejected(self):
  self.d.update(source='https://example.org/official-notice',verified=True,threads_caption='https://example.com\n자세한 사항은 프로필링크 확인')
  rc,exists,*_=self.run_generator();self.assertNotEqual(rc,0);self.assertFalse(exists)
if __name__=='__main__':unittest.main()
