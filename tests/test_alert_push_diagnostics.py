"""Offline incident diagnosis and explicit CAS recovery, with no real delivery."""
import copy
import io
import json
import os
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import run_targeted_push as runner
from scripts import private_onesignal_export_request as exports
from scripts import private_onesignal_export_download as downloads
from scripts import private_rollout_cursor as cursor
from scripts import onesignal_known_subscriber as subscribers


SHA = 'a' * 40
ENV = {'CP_PUSH_MODE': 'diagnose', 'CP_ENABLE_LIVE_PUSH': '0',
       'CP_ENABLE_ALL_OPTED_IN_ROLLOUT': '0',
       'CP_ONESIGNAL_APP_ID': '00000000-0000-4000-8000-000000000001',
       'CP_ONESIGNAL_REST_API_KEY': 'fixture-private-key',
       'CP_LEDGER_REPOSITORY': 'fixture/private-state', 'CP_LEDGER_TOKEN': 'fixture-token'}


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, ENV, clear=True))
        self.ledger = {'delivered': ['1' * 64], 'pending': []}
        self.queue = {'version': 1, 'tasks': {}}
        self.control = {'version': 1, 'state': 'blocked', 'failures': 0,
                        'reason': 'run_fault_review_required', 'owner': 'private-owner',
                        'review': 'private-review-must-not-be-printed'}
        self.preflight = self.stack.enter_context(patch.object(runner, 'preflight', return_value=('fixture/private-state', 'fixture-token')))
        self.read_ledger = self.stack.enter_context(patch.object(runner, 'read_private_ledger', return_value=(self.ledger, SHA)))
        self.read_baseline = self.stack.enter_context(patch.object(runner, 'read_state', return_value=({'ids': ['a1']}, SHA)))
        self.read_queue = self.stack.enter_context(patch.object(runner.queue, 'read_queue', return_value=(self.queue, SHA)))
        self.read_control = self.stack.enter_context(patch.object(runner.circuit, 'read', return_value=(self.control, SHA)))
        self.request_export = self.stack.enter_context(patch.object(exports, 'request_export', return_value='https://files.onesignal.com/private-signed-export?token=hidden'))
        self.read_export = self.stack.enter_context(patch.object(downloads, 'read_export_ids', return_value=['private-subscription-one', 'private-subscription-two']))
        self.read_cursor = self.stack.enter_context(patch.object(cursor, 'read_cursor', return_value=({'version': 1, 'next_index': 0, 'export_hash': ''}, None)))
        self.lookup = self.stack.enter_context(patch.object(subscribers, 'lookup', return_value=None))
        self.save_cursor = self.stack.enter_context(patch.object(cursor, 'save_cursor', side_effect=AssertionError('No cursor write permitted')))
        self.save = self.stack.enter_context(patch.object(runner, 'save_state', side_effect=AssertionError('No state save permitted')))
        self.queue_write = self.stack.enter_context(patch.object(runner.queue, 'write_queue', side_effect=AssertionError('No queue write permitted')))
        self.control_write = self.stack.enter_context(patch.object(runner.circuit, 'write', side_effect=AssertionError('No control write permitted')))
        self.resume = self.stack.enter_context(patch.object(runner.circuit, 'resume', return_value='b' * 40))
        self.session = self.stack.enter_context(patch.object(runner.circuit, 'session', side_effect=AssertionError('No sender session permitted')))
        self.output = self.stack.enter_context(redirect_stdout(io.StringIO()))

    def assert_no_state_change(self):
        self.save.assert_not_called()
        self.queue_write.assert_not_called()
        self.control_write.assert_not_called()
        self.resume.assert_not_called()
        self.session.assert_not_called()
        self.save_cursor.assert_not_called()

    def enable_review(self):
        os.environ.update(CP_PUSH_MODE='resume_after_review', CP_EXPECTED_CONTROL_SHA=SHA,
                          CP_PUSH_REVIEW_REFERENCE='Reviewed incident fixture-run; no inflight delivery')

    def test_blocked_diagnosis_reports_only_safe_counts_and_keeps_circuit(self):
        before = copy.deepcopy((self.ledger, self.queue, self.control))
        report = runner.diagnose()
        self.assertEqual(report['status'], 'diagnostic_complete')
        self.assertEqual(report['export']['parsed_subscription_count'], 2)
        self.assertFalse(report['export']['consent_verified'])
        self.assertEqual(report['lookup']['sample_count'], 1)
        self.lookup.assert_called_once_with('private-subscription-one')
        self.assertEqual(report['control']['state'], 'blocked')
        self.assertEqual(report['control']['sha'], SHA)
        self.assertTrue(report['operator_review_required'])
        self.assertEqual(report['sent'], 0)
        self.assertFalse(report['state_changed'])
        self.assertEqual(before, (self.ledger, self.queue, self.control))
        for private in ('private-subscription', 'private-signed-export', 'fixture-private-key',
                        'fixture-token', 'private-owner', 'private-review'):
            self.assertNotIn(private, self.output.getvalue())
        self.assert_no_state_change()

    def test_diagnose_requires_both_guards_exactly_off_before_any_read(self):
        for name in ('CP_ENABLE_LIVE_PUSH', 'CP_ENABLE_ALL_OPTED_IN_ROLLOUT'):
            for value in ('1', ''):
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                    with self.assertRaisesRegex(RuntimeError, 'both send guards OFF'):
                        runner.main()
        self.preflight.assert_not_called()
        self.read_ledger.assert_not_called()
        self.request_export.assert_not_called()
        self.assert_no_state_change()

    def test_diagnostic_http_failure_exposes_only_stage_and_status(self):
        self.request_export.side_effect = RuntimeError('OneSignal export request rejected (HTTP 403)')
        report = runner.diagnose()
        self.assertEqual(report['stage'], 'export_request')
        self.assertEqual(report['http_status'], 403)
        self.assertEqual(report['error_code'], 'http_rejected')
        self.read_export.assert_not_called()
        self.assert_no_state_change()

    def test_download_and_private_http_errors_do_not_print_url_or_body(self):
        self.read_export.side_effect = HTTPError('https://private.example/token-secret', 403,
                                                 'private-message', {}, io.BytesIO(b'private-body'))
        report = runner.diagnose()
        self.assertEqual((report['stage'], report['http_status']), ('export_download', 403))
        for hidden in ('token-secret', 'private-message', 'private-body', 'private.example'):
            self.assertNotIn(hidden, self.output.getvalue())
        self.assert_no_state_change()

    def test_unknown_exception_and_unrecognized_control_reason_are_redacted(self):
        self.control['reason'] = 'private-subscription-and-token'
        self.request_export.side_effect = RuntimeError('upstream private-subscription-and-token')
        report = runner.diagnose()
        self.assertEqual(report['control']['reason_code'], 'other_redacted')
        self.assertEqual(report['error_code'], 'unclassified_diagnostic_error')
        self.assertNotIn('private-subscription-and-token', self.output.getvalue())
        self.assert_no_state_change()

    def test_rejected_export_host_reports_only_coarse_category(self):
        self.request_export.side_effect = ValueError('Private export URL host not allowed (provider category: aws-s3); configure the exact verified host privately')
        report = runner.diagnose()
        self.assertEqual(report['error_code'], 'export_host_not_allowed')
        self.assertEqual(report['provider_host_category'], 'aws-s3')
        self.assert_no_state_change()

    def test_lookup_failure_pinpoints_stage_and_keeps_circuit(self):
        self.lookup.side_effect = RuntimeError('OneSignal authentication or permissions rejected')
        report = runner.diagnose()
        self.assertEqual(report['stage'], 'subscriber_lookup')
        self.assertEqual(report['error_code'], 'subscriber_lookup_auth_rejected')
        self.assert_no_state_change()

    def test_empty_export_is_safe_without_subscriber_lookup(self):
        self.read_export.return_value = []
        report = runner.diagnose()
        self.assertEqual(report['status'], 'diagnostic_complete')
        self.assertEqual(report['lookup']['sample_count'], 0)
        self.lookup.assert_not_called()
        self.assert_no_state_change()

    def test_cursor_read_error_stops_before_provider_without_writes(self):
        self.read_cursor.side_effect = ValueError('Invalid private push checkpoint')
        report = runner.diagnose()
        self.assertEqual(report['stage'], 'cursor_read')
        self.assertEqual(report['error_code'], 'invalid_private_cursor')
        self.request_export.assert_not_called()
        self.assert_no_state_change()

    def test_missing_baseline_stops_before_provider_without_bootstrapping(self):
        self.read_baseline.return_value = (None, None)
        report = runner.diagnose()
        self.assertEqual(report['stage'], 'baseline_read')
        self.assertEqual(report['error_code'], 'invalid_private_baseline')
        self.request_export.assert_not_called()
        self.assert_no_state_change()

    def test_pending_and_uncertain_history_is_counted_without_reset(self):
        self.ledger['pending'] = ['2' * 64]
        self.queue['tasks'] = {'3' * 64: {'state': 'uncertain'}, '4' * 64: {'state': 'reserved'}}
        before = copy.deepcopy((self.ledger, self.queue))
        report = runner.diagnose()
        self.assertEqual(report['ledger']['pending_count'], 1)
        self.assertEqual(report['queue']['counts']['uncertain'], 1)
        self.assertEqual(report['queue']['counts']['reserved'], 1)
        self.assertEqual(before, (self.ledger, self.queue))
        self.assert_no_state_change()

    def test_failed_diagnostic_mode_signals_failure_and_cannot_resume(self):
        self.read_export.side_effect = RuntimeError('Private export not ready after bounded checks (HTTP 404)')
        with self.assertRaisesRegex(RuntimeError, 'Read-only diagnosis failed'):
            runner.main()
        self.assertEqual(json.loads(self.output.getvalue())['error_code'], 'export_not_ready_after_bounded_checks')
        self.assert_no_state_change()

    def test_resume_requires_exact_sha_and_bounded_reference_before_network(self):
        for sha, reference in (('', 'review'), ('x' * 40, 'review'), (SHA, ''),
                               (SHA, 'a' * 161), (SHA, 'bad\nreference')):
            self.enable_review()
            with self.subTest(sha=sha, reference_length=len(reference)), \
                    patch.dict(os.environ, {'CP_EXPECTED_CONTROL_SHA': sha, 'CP_PUSH_REVIEW_REFERENCE': reference}):
                with self.assertRaises(RuntimeError):
                    runner.resume_after_review()
        self.preflight.assert_not_called()
        self.read_ledger.assert_not_called()
        self.request_export.assert_not_called()
        self.assert_no_state_change()

    def test_resume_requires_both_send_guards_off(self):
        self.enable_review()
        with patch.dict(os.environ, {'CP_ENABLE_LIVE_PUSH': '1'}):
            with self.assertRaisesRegex(RuntimeError, 'both send guards OFF'):
                runner.main()
        self.preflight.assert_not_called()
        self.assert_no_state_change()

    def test_resume_rejects_stale_or_nonblocked_state_before_provider(self):
        self.enable_review()
        for state, sha in (('blocked', 'b' * 40), ('ready', SHA), ('armed', SHA)):
            self.read_control.return_value = (dict(self.control, state=state), sha)
            with self.subTest(state=state, sha=sha):
                with self.assertRaisesRegex(RuntimeError, 'not a reviewed blocked state'):
                    runner.resume_after_review()
        self.request_export.assert_not_called()
        self.assert_no_state_change()

    def test_resume_rejects_ledger_pending_without_reset(self):
        self.enable_review()
        self.ledger['pending'] = ['2' * 64]
        with self.assertRaisesRegex(RuntimeError, 'Unresolved prior delivery'):
            runner.resume_after_review()
        self.assertEqual(self.ledger['pending'], ['2' * 64])
        self.request_export.assert_not_called()
        self.assert_no_state_change()

    def test_resume_rejects_reserved_and_uncertain_tasks_without_reset(self):
        self.enable_review()
        for state in ('reserved', 'uncertain'):
            self.queue['tasks'] = {'3' * 64: {'state': state}}
            with self.subTest(state=state), self.assertRaisesRegex(RuntimeError, 'Unresolved prior delivery'):
                runner.resume_after_review()
            self.assertEqual(self.queue['tasks']['3' * 64]['state'], state)
        self.request_export.assert_not_called()
        self.assert_no_state_change()

    def test_resume_requires_successful_current_provider_diagnosis(self):
        self.enable_review()
        self.request_export.side_effect = RuntimeError('OneSignal export request rejected (HTTP 403)')
        with self.assertRaisesRegex(RuntimeError, 'diagnosis failed'):
            runner.resume_after_review()
        self.assert_no_state_change()

    def test_resume_detects_control_change_during_provider_check(self):
        self.enable_review()
        self.read_control.side_effect = [(self.control, SHA), (self.control, SHA), (self.control, 'b' * 40)]
        with self.assertRaisesRegex(RuntimeError, 'Control changed'):
            runner.resume_after_review()
        self.assert_no_state_change()

    def test_resume_detects_new_inflight_task_during_provider_check(self):
        self.enable_review()
        inflight = {'version': 1, 'tasks': {'3' * 64: {'state': 'reserved'}}}
        self.read_queue.side_effect = [(self.queue, SHA), (self.queue, SHA), (inflight, SHA)]
        with self.assertRaisesRegex(RuntimeError, 'Unresolved prior delivery'):
            runner.resume_after_review()
        self.assert_no_state_change()

    def test_explicit_review_uses_existing_cas_and_preserves_all_history(self):
        self.enable_review()
        self.queue['tasks'] = {'3' * 64: {'state': 'pending'}, '4' * 64: {'state': 'accepted', 'message_id': 'private-provider-id'}}
        before = copy.deepcopy((self.ledger, self.queue, self.control))
        runner.main()
        self.resume.assert_called_once_with(SHA,
            evidence='Reviewed incident fixture-run; no inflight delivery', confirmed_no_inflight=True)
        self.assertEqual(before, (self.ledger, self.queue, self.control))
        self.save.assert_not_called()
        self.queue_write.assert_not_called()
        self.control_write.assert_not_called()
        self.session.assert_not_called()
        reports = [json.loads(line) for line in self.output.getvalue().splitlines()]
        self.assertEqual([row['sent'] for row in reports], [0, 0])
        self.assertTrue(reports[-1]['history_preserved'])
        self.assertNotIn('private-provider-id', self.output.getvalue())

    def test_scheduled_run_never_enters_diagnose_or_resume_modes(self):
        with patch.dict(os.environ, {'CP_PUSH_MODE': 'run'}), \
                patch.object(runner, 'run') as run, patch.object(runner, 'diagnose') as diagnose, \
                patch.object(runner, 'resume_after_review') as resume:
            runner.main()
        run.assert_called_once_with()
        diagnose.assert_not_called()
        resume.assert_not_called()


if __name__ == '__main__':
    unittest.main()
