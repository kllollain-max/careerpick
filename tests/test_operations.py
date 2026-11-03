import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from scripts.run_operations import run, validate
ROOT=Path(__file__).resolve().parents[1]

class OperationsTests(unittest.TestCase):
    def execute(self,collector):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            originals={n:(ROOT/n).read_bytes() for n in ('alio.json','alio-detail.json')}
            for n,b in originals.items():(root/n).write_bytes(b)
            report=run(root,collector)
            self.assertTrue(report['originals_preserved'])
            self.assertTrue(all((root/n).read_bytes()==b for n,b in originals.items()))
            return report
    def test_unchanged(self):
        r=self.execute(lambda root:dict(status='collected',changed=False,received=509))
        self.assertEqual(r['status'],'unchanged')
        self.assertEqual(r['counts']['deleted'],0)
    def test_partial_failure_preserved(self):
        self.assertEqual(self.execute(lambda root:dict(status='collection_failed_preserved'))['status'],'failed_preserved')
    def test_drop_preserved(self):
        self.assertEqual(self.execute(lambda root:dict(status='collected',changed=False,received=1))['status'],'failed_preserved')
    def test_empty_candidate_preserved(self):
        def empty(root):
            (root/'alio.json').write_text('{"posts":[]}')
            return dict(status='collected',changed=True,received=509)
        self.assertEqual(self.execute(empty)['status'],'failed_preserved')
    def test_duplicate_rejected(self):
        feed=json.loads((ROOT/'alio.json').read_text());details=json.loads((ROOT/'alio-detail.json').read_text())
        feed['posts'].append(copy.deepcopy(feed['posts'][0]))
        with self.assertRaises(ValueError):validate(feed,details)
    def test_detail_failure_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for n in ('alio.json','alio-detail.json'):(root/n).write_bytes((ROOT/n).read_bytes())
            def fail(sn):raise RuntimeError('simulated')
            r=run(root,lambda root:dict(status='collected',changed=False,received=509),fail)
            self.assertEqual(r['status'],'failed_preserved')
            self.assertTrue(r['originals_preserved'])
if __name__=='__main__':unittest.main()
