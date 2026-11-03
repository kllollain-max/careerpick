import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from scripts.threads_auto import validate_candidate, candidates
from scripts.threads_migration_audit import collect, main


class MigrationTests(unittest.TestCase):
    def test_new_project_link_and_old_host(self):
        job = {'id': 'a1', 'org': '기관', 'title': '채용', 'due': '2026-11-12'}
        self.assertTrue(validate_candidate(dict(job, url='https://kllollain-max.github.io/careerpick/jobs/a1.html'), date(2026,11,3)))
        self.assertFalse(validate_candidate(dict(job, url='https://jobinfo-hub.github.io/jobs/a1.html'), date(2026,11,3)))

    def test_read_only_pagination(self):
        replies = iter([{'data':[{'id':'1'}], 'paging':{'next':'not-followed', 'cursors':{'after':'page2'}}}, {'data':[{'id':'2'}]}])
        calls = []
        posts, complete = collect(lambda m,p,a: (calls.append((m,p,a)) or next(replies)))
        self.assertTrue(complete)
        self.assertEqual([p['id'] for p in posts], ['1','2'])
        self.assertTrue(all(c[0] == 'GET' and c[1] == '/me/threads' for c in calls))

    def test_ambiguous_paging_is_incomplete(self):
        _, complete = collect(lambda *a: {'data':[], 'paging':{'next':'present'}})
        self.assertFalse(complete)

    def test_missing_token_performs_no_request(self):
        with patch.dict(os.environ, {'THREADS_ACCESS_TOKEN':''}), patch('scripts.threads_migration_audit.api') as api:
            with self.assertRaises(SystemExit): main()
            api.assert_not_called()

    def test_backup_history_preserved(self):
        history = json.loads(Path('threads_posted.json').read_text())
        self.assertGreaterEqual(len(history['records']), 39)
        self.assertGreaterEqual(sum(r['status']=='published' for r in history['records']),33)
        self.assertTrue(any(r.get('threads_post_id')=='18158776393451353' and r['status']=='published' for r in history['records']))

    def test_activation_barrier_and_new_images(self):
        workflow = Path('.github/workflows/threads_auto.yml').read_text()
        self.assertIn("vars.THREADS_MIGRATION_READY == 'true'", workflow)
        self.assertIn('THREADS_NEW_CONTENT: "false"', workflow)
        self.assertIn('THREADS_CLAIM_BRANCH: threads-publisher-state', workflow)
        self.assertNotIn('deploy.yml/dispatches', workflow)
        self.assertEqual(workflow.count('    - cron:'),4)
        self.assertIn('raw.githubusercontent.com/kllollain-max/careerpick/main/threads-images/',Path('scripts/threads_auto.py').read_text())


if __name__ == '__main__': unittest.main()
