import datetime,json,tempfile,unittest
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch
from run_offline import run
class OfflinePipelineTests(unittest.TestCase):
 def test_expired_and_uncertain_no_output(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);src=p/"jobs.json";dst=p/"out"
   src.write_text(json.dumps([{"id":"a1","official_url":"https://job.alio.go.kr","official_verified":True,"headcount":10,"employment_type":"정규직","application_deadline":"2020-01-01 18:00","deadline_evidence":{"kind":"official_application_deadline","quote":"접수마감 2020-01-01 18:00","reviewed":True}},{"id":"a2","official_url":"https://job.alio.go.kr","official_verified":True,"headcount":99,"employment_type":"정규직","application_deadline":"2099-12-31"}]),encoding="utf-8")
   result=run(src,dst)
   self.assertEqual(result["created"],0)
   self.assertFalse(dst.exists())
 def test_existing_output_unchanged(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);src=p/"jobs.json";dst=p/"out";dst.mkdir();(dst/"keep").write_text("safe")
   src.write_text("[]")
   with self.assertRaises(FileExistsError):run(src,dst)
   self.assertEqual((dst/"keep").read_text(),"safe")

 def test_valid_job_produces_three_png_and_zip(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);src=p/"jobs.json";dst=p/"out"
   row={"id":"a123","organization":"검증기관","title":"정규직 채용","official_url":"https://job.alio.go.kr/notice","official_verified":True,"headcount":12,"employment_type":"정규직","application_deadline":"2099-12-31 18:00","deadline_evidence":{"kind":"official_application_deadline","quote":"접수마감 2099-12-31 18:00","application_deadline":"2099-12-31 18:00","reviewed":True}}
   src.write_text(json.dumps([row],ensure_ascii=False),encoding="utf-8")
   from PIL import Image
   with patch("run_offline.render",return_value=Image.new("RGB",(1080,1350),"white")):
    result=run(src,dst)
   self.assertEqual(result["created"],1)
   self.assertEqual(len(list((dst/"a123").glob("card_*.png"))),3)
   import zipfile
   with zipfile.ZipFile(dst/"a123"/"cardnews.zip") as z:
    self.assertIsNone(z.testzip())
   manifest=json.loads((dst/"manifest.json").read_text(encoding="utf-8"))
   self.assertEqual(manifest["jobs"][0]["visual_review"],"PENDING")
   self.assertEqual(manifest["publication"],"disabled")
 def test_render_failure_leaves_no_partial_output(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);src=p/"jobs.json";dst=p/"out"
   row={"id":"a123","organization":"검증기관","title":"정규직 채용","official_url":"https://job.alio.go.kr/notice","official_verified":True,"headcount":12,"employment_type":"정규직","application_deadline":"2099-12-31 18:00","deadline_evidence":{"kind":"official_application_deadline","quote":"접수마감 2099-12-31 18:00","application_deadline":"2099-12-31 18:00","reviewed":True}}
   src.write_text(json.dumps([row],ensure_ascii=False),encoding="utf-8")
   with patch("run_offline.render",side_effect=RuntimeError("image renderer failed")):
    with self.assertRaises(RuntimeError):run(src,dst)
   self.assertFalse(dst.exists())

if __name__=="__main__":unittest.main()
