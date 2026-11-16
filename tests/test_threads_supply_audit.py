import copy
import io
import unittest
import urllib.error
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo
from scripts.threads_supply_audit import audit_slots, build_handoff, persist_handoff
from scripts.threads_queue_bridge import future_slots, verified_supply_status
from scripts.threads_http import read_response

KST = ZoneInfo('Asia/Seoul')

class SupplyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 14, 0, tzinfo=KST)
        self.history = {'records': [], 'posted_ids': []}

    def test_eight_kst_slots_identical_for_utc_caller(self):
        slots = future_slots(self.now)
        self.assertEqual(len(slots), 8)
        self.assertEqual(slots[0], '2026-11-16T16:00:00+09:00')
        self.assertEqual(slots[-1], '2026-11-18T12:00:00+09:00')
        self.assertEqual(slots, future_slots(self.now.astimezone(ZoneInfo('UTC'))))
        with self.assertRaisesRegex(ValueError, 'NOW_TIMEZONE'):
            future_slots(self.now.replace(tzinfo=None))

    @patch('scripts.threads_queue_bridge.verify_entry', side_effect=ValueError('REVIEW_SOURCE_STALE'))
    def test_eight_ready_flags_are_not_eight_approved_drafts(self, verify):
        entries = [{'notice_id': str(i), 'scheduled_at': slot, 'writer': {'status': 'ready'}}
                   for i, slot in enumerate(future_slots(self.now))]
        status = verified_supply_status(entries, self.now, self.history, {}, {}, {})
        self.assertEqual(status['approved_inventory_count'], 0)
        self.assertEqual(status['inventory_shortfall'], 8)
        self.assertTrue(status['replenishment_required'])
        self.assertEqual(len(status['invalid_ready_entries']), 8)

    def test_no_post_id_and_test_receipts_cannot_mask_missing_noon_post(self):
        slot = '2026-11-16T12:00:00+09:00'
        self.history['records'] = [
            {'scheduled_at': slot, 'status': 'published'},
            {'scheduled_at': slot, 'status': 'published', 'threads_post_id': 'test', 'test_only': True}]
        report = audit_slots(self.history, self.now)
        noon = next(r for r in report['slots'] if r['scheduled_at'] == slot)
        self.assertEqual(noon['status'], 'missing_receipt')
        self.assertEqual(report['recorded_publications'], 0)
        self.assertFalse(report['live_meta_verification_performed'])

    def test_ambiguous_reservation_is_not_safe_to_republish(self):
        self.history['records'] = [{'scheduled_at': '2026-11-16T12:00:00+09:00', 'status': 'pending'}]
        report = audit_slots(self.history, self.now)
        self.assertEqual(report['slots'][-1]['status'], 'unresolved_pending')
        self.assertEqual(report['recorded_publications'], 0)

    def test_real_receipt_is_separate_from_live_meta_verification(self):
        self.history['records'] = [{'scheduled_at': '2026-11-16T03:00:00+00:00',
                                   'status': 'published', 'threads_post_id': '123'}]
        report = audit_slots(self.history, self.now)
        self.assertEqual(report['slots'][-1]['status'], 'recorded_publication')
        self.assertEqual(report['recorded_publications'], 1)
        self.assertFalse(report['live_meta_verification_performed'])

    def test_handoff_rejects_automatic_approval_flags(self):
        with self.assertRaisesRegex(ValueError, 'UNSAFE_HANDOFF'):
            build_handoff({}, {'automatic_approval': True}, {}, {}, self.history, self.now)

    def test_cas_conflict_reloads_sha_and_has_bounded_retry(self):
        old = {'captured_at': '2026-11-16T13:00:00+09:00'}
        new = {'captured_at': self.now.isoformat()}
        reader = Mock(side_effect=[(old, 'sha1'), (old, 'sha2'), (new, 'sha3')])
        conflict = urllib.error.HTTPError('https://example.com', 409, '', {}, io.BytesIO())
        writer = Mock(side_effect=[conflict, {}]); sleeper = Mock()
        digest = persist_handoff(new, 'not-a-secret', reader, writer, sleeper)
        self.assertEqual(len(digest), 64)
        self.assertEqual(writer.call_count, 2)
        self.assertEqual(writer.call_args_list[1].args[3]['sha'], 'sha2')
        sleeper.assert_called_once_with(1)
        reader = Mock(return_value=(old, 'sha1'))
        writer = Mock(side_effect=conflict)
        with self.assertRaises(urllib.error.HTTPError):
            persist_handoff(new, 'not-a-secret', reader, writer, Mock())
        self.assertEqual(writer.call_count, 3)

    def test_newer_handoff_is_never_overwritten(self):
        reader = Mock(return_value=({'captured_at': '2026-11-16T15:00:00+09:00'}, 'newer'))
        writer = Mock()
        with self.assertRaisesRegex(ValueError, 'NEWER_HANDOFF_ALREADY_EXISTS'):
            persist_handoff({'captured_at': self.now.isoformat()}, '', reader, writer)
        writer.assert_not_called()

    def test_user_ranking_keeps_employment_and_unit_count_above_popularity(self):
        from scripts.threads_v5 import ranking_key
        base = {'employment_priority': 0, 'unit_count': 3, 'unit_scope': 'reviewed_unit',
                'application_period': {'end': '2026-11-30T17:00:00+09:00'}, 'notice_id': 'x'}
        popular = {**base, 'employment_priority': 2, 'interest':
                   {'verified': True, 'observation_ids': ['real-observation'], 'score': 100}}
        self.assertLess(ranking_key(base), ranking_key(popular))
        bigger = {**base, 'unit_count': 4}
        self.assertLess(ranking_key(bigger), ranking_key(base))
        preferred = {**base, 'sector_priority': 0}
        self.assertLess(ranking_key(preferred), ranking_key(base))

    def test_transient_reads_backoff_then_stop_and_posts_are_never_replayed(self):
        import urllib.request
        sleeper = Mock(); opener = Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):
            read_response(urllib.request.Request('https://example.com'), opener=opener, sleeper=sleeper)
        self.assertEqual(opener.call_count, 3)
        self.assertEqual([c.args[0] for c in sleeper.call_args_list], [2, 4])
        opener.reset_mock()
        with self.assertRaises(ValueError):
            read_response(urllib.request.Request('https://example.com', data=b''), opener=opener)
        opener.assert_not_called()

if __name__ == '__main__':
    unittest.main()
