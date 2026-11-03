import json,tempfile,unittest
from pathlib import Path
import mpm_exam
from scripts.run_exam_operations import run,ROOT,PATH
class ExamOperationTests(unittest.TestCase):
 def test_existing_blank_source_fields_are_normalized_and_unchanged(self):
  data=json.loads((ROOT/PATH).read_text())
  rows=mpm_exam.validate_records(data['records'])['records']
  class Client:
   def __init__(self,key):pass
   def collect(self):return {'records':rows,'verification':{'total_rows':len(rows)}}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/PATH;p.parent.mkdir(parents=True);p.write_text(json.dumps(data));before=p.read_bytes()
   r=run(root,Client);self.assertEqual(r['status'],'unchanged');self.assertTrue(r['original_preserved']);self.assertEqual(p.read_bytes(),before)
 def test_error_keeps_calendar(self):
  class Client:
   def __init__(self,key):raise TimeoutError()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/PATH;p.parent.mkdir(parents=True);p.write_bytes((ROOT/PATH).read_bytes())
   r=run(root,Client);self.assertEqual(r['status'],'failed_preserved');self.assertTrue(r['original_preserved'])
