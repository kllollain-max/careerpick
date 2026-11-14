import datetime,json,tempfile,unittest
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch
from run_offline import run
class OfflinePipelineTests(unittest.TestCase):
 def test_expired_and_uncertain_no_output(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);src=p/"jobs.json";dst=p/"out"
   src.write_text(json.dumps([{"id":"a1","official_url":"https://example.org","official_verified":True,"headcount":10,"employment_type":"정규직","application_deadline":"2020-01-01 18:00"},{"id":"a2","official_url":"https://example.org","official_verified":True,"headcount":99,"employment_type":"정규직","application_deadline":"2099-12-31"}]),encoding="utf-8")
   result=run(src,dst)
   self.assertEqual(result["created"],0)
   self.assertFalse(dst.exists())
 def test_existing_output_unchanged(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);src=p/"jobs.json";dst=p/"out";dst.mkdir();(dst/"keep").write_text("safe")
   src.write_text("[]")
   with self.assertRaises(FileExistsError):run(src,dst)
   self.assertEqual((dst/"keep").read_text(),"safe")
if __name__=="__main__":unittest.main()
