import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import run_targeted_push as runner
from scripts.onesignal_guarded_transport import build_payload


class RecoveryTests(unittest.TestCase):
    def test_missing_credentials_do_not_call_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(runner, '_request') as network:
            with self.assertRaisesRegex(RuntimeError, 'Missing GitHub Secrets'):
                runner.preflight()
            network.assert_not_called()

    def test_public_storage_rejected_before_writes(self):
        with patch.dict(os.environ, {key: 'fixture' for key in runner.REQUIRED}), \
                patch.object(runner, '_config', return_value=('owner/state', 'fixture')), \
                patch.object(runner, '_request', return_value={'private': False}) as network:
            with self.assertRaisesRegex(RuntimeError, 'must be private'):
                runner.preflight()
            self.assertEqual(network.call_count, 1)

    def test_unknown_mode_rejected_before_network(self):
        with patch.dict(os.environ, {'CP_PUSH_MODE': 'broadcast'}), patch.object(runner, 'preflight') as preflight:
            with self.assertRaises(RuntimeError): runner.main()
            preflight.assert_not_called()

    def test_run_without_enable_has_no_writes(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(runner, 'save_state') as save:
            with self.assertRaisesRegex(RuntimeError, 'OFF'): runner.run()
            save.assert_not_called()

    def test_uncertain_history_prevents_bootstrap_resume(self):
        with patch.object(runner, 'read_state', return_value=({}, 'existing')), \
                patch.object(runner, 'read_private_ledger', return_value=({'pending': ['held']}, 'sha')), \
                patch.object(runner.queue, 'read_queue', return_value=({'tasks': {}}, 'sha')), \
                patch.object(runner.circuit, 'resume') as resume, patch.object(runner, 'save_state') as save:
            with self.assertRaisesRegex(RuntimeError, 'Unresolved'): runner.initialize()
            resume.assert_not_called()
            save.assert_not_called()

    def test_baseline_advances_only_after_candidate_handoff(self):
        with patch.dict(os.environ, {'CP_ENABLE_LIVE_PUSH':'1','CP_ENABLE_ALL_OPTED_IN_ROLLOUT':'1'}), \
                tempfile.TemporaryDirectory() as directory, \
                patch.object(runner.detection, 'STATE', Path(directory)/'baseline.json'), \
                patch.object(runner, 'read_state', return_value=({'ids':['a1']},'sha')), \
                patch.object(runner.detection, 'main', side_effect=RuntimeError('storage failed')), \
                patch.object(runner, 'save_state') as save:
            with self.assertRaises(RuntimeError): runner.run()
            save.assert_not_called()

    def test_first_party_job_link_not_data_supplied_url(self):
        payload=build_payload({'id':'a306597','title':'채용','url':'https://invalid.example/'}, 'fixture','app')
        self.assertEqual(payload['url'],'https://kllollain-max.github.io/careerpick/jobs/a306597.html')
        self.assertEqual(payload['include_subscription_ids'],['fixture'])
        self.assertNotIn('included_segments',payload)
