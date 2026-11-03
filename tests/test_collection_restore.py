import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta
import alio
from scripts.collect_alio import collect

class CollectionRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.original = {'updated':'2026-10-30T23:43:53+09:00','posts':[{'id':'a1','title':'archive','due':'2020-01-01'}]}
        (self.root/'alio.json').write_text(json.dumps(self.original))
        (self.root/'alio-detail.json').write_text('{"a1":{"recrutPblntSn":"1"}}')
        self.before = [p.read_bytes() for p in (self.root/'alio.json', self.root/'alio-detail.json')]
    def tearDown(self): self.tmp.cleanup()
    def test_missing_secret_preserves(self):
        with patch.dict(os.environ, {'ALIO_KEY':''}): self.assertFalse(collect(self.root)['changed'])
        self.assertEqual(self.before,[p.read_bytes() for p in (self.root/'alio.json',self.root/'alio-detail.json')])
    def test_failed_call_preserves_both_files(self):
        with patch.dict(os.environ, {'ALIO_KEY':'fixture'}),patch.object(alio,'call',side_effect=TimeoutError): self.assertFalse(collect(self.root)['changed'])
        self.assertEqual(self.before,[p.read_bytes() for p in (self.root/'alio.json',self.root/'alio-detail.json')])
    def test_success_deduplicates_and_retains_archive(self):
        row={'recrutPblntSn':'2','recrutPbancTtl':'fixture','instNm':'test','pbancEndYmd':(datetime.now(alio.KST)+timedelta(days=30)).strftime('%Y%m%d')}
        with patch.dict(os.environ, {'ALIO_KEY':'fixture'}),patch.object(alio,'call',return_value={'totalCount':2,'result':[row,row]}): result=collect(self.root)
        self.assertTrue(result['changed']); self.assertEqual(result['new_ids'],1)
        self.assertEqual({p['id'] for p in json.loads((self.root/'alio.json').read_text())['posts']},{'a1','a2'})
        self.assertEqual(set(json.loads((self.root/'alio-detail.json').read_text())),{'a1','a2'})
