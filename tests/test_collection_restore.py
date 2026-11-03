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
    def test_success_retains_archive_with_unique_official_ids(self):
        row={'recrutPblntSn':'2','recrutPbancTtl':'fixture','instNm':'test','pbancEndYmd':(datetime.now(alio.KST)+timedelta(days=30)).strftime('%Y%m%d')}
        with patch.dict(os.environ, {'ALIO_KEY':'fixture'}),patch.object(alio,'call',return_value={'totalCount':1,'result':[row]}): result=collect(self.root)
        self.assertTrue(result['changed']); self.assertEqual(result['new_ids'],1)
        self.assertEqual({p['id'] for p in json.loads((self.root/'alio.json').read_text())['posts']},{'a1','a2'})
        self.assertEqual(set(json.loads((self.root/'alio-detail.json').read_text())),{'a1','a2'})

    def test_duplicate_response_is_failed_and_both_files_are_preserved(self):
        row={'recrutPblntSn':'2','recrutPbancTtl':'fixture','instNm':'test','pbancEndYmd':'20501231'}
        with patch.dict(os.environ, {'ALIO_KEY':'fixture'}),patch.object(alio,'call',return_value={'totalCount':2,'result':[row,row]}):
            result=collect(self.root)
        self.assertEqual(result['status'], 'collection_failed_preserved')
        self.assertFalse(result['changed'])
        self.assertEqual(self.before,[p.read_bytes() for p in (self.root/'alio.json',self.root/'alio-detail.json')])

    def test_successful_unchanged_collection_preserves_bytes_and_is_success(self):
        row={'recrutPblntSn':'2','recrutPbancTtl':'fixture','instNm':'test',
             'pbancBgngYmd':'20261101','pbancEndYmd':'20501231'}
        with patch.dict(os.environ, {'ALIO_KEY':'fixture'}),patch.object(alio,'call',return_value={'totalCount':1,'result':[row]}):
            first=collect(self.root)
            self.assertTrue(first['changed'])
            before=[p.read_bytes() for p in (self.root/'alio.json',self.root/'alio-detail.json')]
            second=collect(self.root)
        self.assertEqual(second['status'], 'collected')
        self.assertFalse(second['changed'])
        self.assertEqual(second['received'], 1)
        self.assertEqual(second['retained'], 2)
        self.assertEqual(before,[p.read_bytes() for p in (self.root/'alio.json',self.root/'alio-detail.json')])

    def test_detail_only_change_is_applied_and_archive_remains(self):
        row={'recrutPblntSn':'2','recrutPbancTtl':'fixture','instNm':'test',
             'pbancBgngYmd':'20261101','pbancEndYmd':'20501231','prefCn':'first'}
        with patch.dict(os.environ, {'ALIO_KEY':'fixture'}),patch.object(alio,'call',return_value={'totalCount':1,'result':[row]}):
            collect(self.root)
        changed={**row,'prefCn':'revised preference'}
        with patch.dict(os.environ, {'ALIO_KEY':'fixture'}),patch.object(alio,'call',return_value={'totalCount':1,'result':[changed]}):
            result=collect(self.root)
        self.assertEqual(result['status'], 'collected')
        self.assertTrue(result['changed'])
        details=json.loads((self.root/'alio-detail.json').read_text())
        self.assertEqual(details['a2']['prefCn'],'revised preference')
        self.assertIn('a1',details)

