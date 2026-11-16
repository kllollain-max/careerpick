"""Exercise production CLI and bridge wiring, rather than mocked validators."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import threads_queue_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]


class WorkflowEntrypoints(unittest.TestCase):
    def test_official_notice_routing_does_not_use_external_application_vendor(self):
        post = {'url': 'https://job.alio.go.kr/recruitview.do?idx=306752',
                'src': 'http://kirams.recruiter.co.kr'}
        self.assertEqual(bridge.official_notice_url(post), post['url'])
        self.assertIsNone(bridge.official_notice_url({'url': post['src']}))
        self.assertIsNone(bridge.official_notice_url({'url': 'https://job.alio.go.kr.evil.test/'}))

    def test_direct_cli_imports_without_pythonpath(self):
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        for script in ('threads_reviewed_ingest.py', 'threads_official_review_pack.py'):
            result = subprocess.run([sys.executable, str(ROOT/'scripts'/script), '--help'],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_bridge_run_reaches_real_selector_with_supported_limit(self):
        empty = {'schema_version': 1, 'entries': []}
        # Do not mock build_selection: an invalid limit previously crashed
        # every live preflight even though the unit promotion tests passed.
        with patch.dict(os.environ, {'THREADS_CLAIM_TOKEN': 'test-only',
                                     'GITHUB_REPOSITORY': 'kllollain-max/careerpick'}), \
             patch.object(bridge, 'read', return_value=(empty, 'fixture-sha')), \
             patch.object(bridge, 'load', return_value={'records': [], 'posted_ids': []}), \
             patch.object(bridge, 'writer_inputs', return_value=(
                 {'max_source_age_hours': 24}, {'posts': []}, {})):
            result = bridge.run(apply=False)
        self.assertEqual(result['source_candidate_count'], 0)
        self.assertTrue(result['next_slot_missing'])
        self.assertFalse(result['queue_updated'])
        self.assertFalse(result['meta_posted'])


if __name__ == '__main__':
    unittest.main()
