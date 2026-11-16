"""Delayed scheduled Threads slots: never POST twice and never hide unverified state."""
import copy
import os
import unittest
from datetime import datetime
from unittest.mock import patch

from scripts import threads_auto


class AlreadyVerifiedSlotTests(unittest.TestCase):
    def setUp(self):
        self.slot = datetime.fromisoformat('2026-11-16T20:00:00+09:00')
        self.now = datetime.fromisoformat('2026-11-16T20:56:00+09:00')
        self.receipt = {
            'job_id': 'a306752',
            'scheduled_at': self.slot.isoformat(),
            'reserved_date': '2026-11-16',
            'status': 'published',
            'threads_post_id': '18134891626705962',
            'public_output_verification': {
                'status': 'verified',
                'post_id': '18134891626705962',
                'permalink': 'https://www.threads.com/@hid_119/post/DfzQXwBGxOw',
                'own_replies_status': 'verified',
            },
        }
        self.env = {
            'GITHUB_RUN_ATTEMPT': '1',
            'THREADS_SCHEDULE_CRON': '0 11 * * *',
            'THREADS_MANUAL_PUBLISH': 'false',
            'THREADS_RECOVERY_SLOT': '',
            'THREADS_RECOVERY_CONFIRMATION': '',
        }

    def test_delayed_cron_with_exact_meta_receipt_skips_without_queue_or_new_post(self):
        history = {'records': [copy.deepcopy(self.receipt)]}
        with patch.dict(os.environ, self.env), \
                patch.object(threads_auto, 'current_publication_slot', return_value=self.slot), \
                patch.object(threads_auto, 'writer_inputs') as writer, \
                patch.object(threads_auto, 'save') as save:
            threads_auto.prepare_master(history, self.now, 'late-schedule')
            self.assertEqual(len(history['records']), 1)
            writer.assert_not_called()
            save.assert_not_called()
        self.assertTrue(threads_auto.verified_published_slot(history, self.slot))

    def test_missing_or_mismatched_meta_receipt_is_not_safe_to_skip(self):
        for alteration in [
            {'public_output_verification': None},
            {'threads_post_id': None},
            {'status': 'pending'},
            {'public_output_verification': {'status': 'verified', 'post_id': 'different'}},
            {'public_output_verification': {
                'status': 'verified', 'post_id': '18134891626705962',
                'own_replies_status': 'unverified',
                'permalink': 'https://www.threads.com/@hid_119/post/DfzQXwBGxOw'}},
        ]:
            with self.subTest(alteration=alteration):
                record = {**self.receipt, **alteration}
                history = {'records': [record]}
                self.assertFalse(threads_auto.verified_published_slot(history, self.slot))
                with patch.dict(os.environ, self.env), \
                        patch.object(threads_auto, 'current_publication_slot',
                                     return_value=self.slot):
                    with self.assertRaisesRegex(RuntimeError, 'Slot already reserved'):
                        threads_auto.prepare_master(history, self.now, 'late-schedule')

    def test_duplicate_slot_records_and_manual_dispatch_never_silently_skip(self):
        history = {'records': [copy.deepcopy(self.receipt), copy.deepcopy(self.receipt)]}
        self.assertFalse(threads_auto.verified_published_slot(history, self.slot))
        with patch.dict(os.environ, self.env), \
                patch.object(threads_auto, 'current_publication_slot',
                             return_value=self.slot):
            with self.assertRaisesRegex(RuntimeError, 'Slot already reserved'):
                threads_auto.prepare_master(history, self.now, 'late-schedule')

        history = {'records': [copy.deepcopy(self.receipt)]}
        with patch.dict(os.environ, {**self.env, 'THREADS_MANUAL_PUBLISH': 'true'}), \
                patch.object(threads_auto, 'current_publication_slot',
                             return_value=self.slot):
            with self.assertRaisesRegex(RuntimeError, 'Slot already reserved'):
                threads_auto.prepare_master(history, self.now, 'manual-repeat')


if __name__ == '__main__':
    unittest.main()
