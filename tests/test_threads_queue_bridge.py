"""No-network regressions for verified queue CAS feeder."""
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import threads_queue_bridge as bridge


class ReviewedBridgeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 12, 25, tzinfo=ZoneInfo('Asia/Seoul'))
        self.history = {'posted_ids': [], 'records': []}
        self.queue = {'schema_version': 1, 'entries': []}
        self.entry = {'notice_id': 'a306965',
                      'scheduled_at': '2026-11-15T16:00:00+09:00',
                      'writer': {'status': 'ready', 'post_text': 'verified'}}
        self.staged = {'schema_version': 1, 'entries': [self.entry]}

    def check(self):
        return bridge.merge(self.queue, self.staged, self.history, {}, {}, {}, self.now)

    def test_no_past_slots(self):
        slots = bridge.future_slots(self.now)
        self.assertEqual(slots[0], '2026-11-15T16:00:00+09:00')
        self.assertNotIn('2026-11-15T12:00:00+09:00', slots)

    def test_no_stage_never_promotes(self):
        self.staged['entries'] = []
        out, accepted, failed = self.check()
        self.assertFalse(accepted)
        self.assertEqual(out, self.queue)

    def test_success_only_after_full_validator(self):
        with patch.object(bridge, 'verify_entry', return_value={'job_id': 'a306965'}) as verified:
            out, accepted, failed = self.check()
        self.assertEqual(len(accepted), 1)
        verified.assert_called_once()
        self.assertEqual(len(out['entries']), 1)
        self.assertEqual(self.queue['entries'], [])

    def test_published_duplicate_blocked(self):
        self.history['posted_ids'].append('a306965')
        _, accepted, failed = self.check()
        self.assertFalse(accepted)
        self.assertEqual(failed[0]['reason'], 'DUPLICATE_POST')

    def test_pending_duplicate_blocked(self):
        self.history['records'].append({'job_id': 'a306965', 'status': 'pending'})
        _, accepted, failed = self.check()
        self.assertFalse(accepted)
        self.assertEqual(failed[0]['reason'], 'DUPLICATE_POST')

    def test_slot_collision_blocked(self):
        self.queue['entries'].append({'scheduled_at': self.entry['scheduled_at'], 'notice_id': 'a00001'})
        _, accepted, failed = self.check()
        self.assertFalse(accepted)
        self.assertEqual(failed[0]['reason'], 'SLOT_ALREADY_OCCUPIED')

    def test_unapproved_draft_blocked(self):
        self.entry['writer']['status'] = 'hold'
        _, accepted, failed = self.check()
        self.assertFalse(accepted)
        self.assertEqual(failed[0]['reason'], 'STAGED_NOT_READY')

    def test_stale_source_blocked(self):
        with patch.object(bridge, 'validate_entry', side_effect=ValueError('SOURCE_CHANGED')):
            _, accepted, failed = self.check()
        self.assertFalse(accepted)
        self.assertEqual(failed[0]['reason'], 'SOURCE_CHANGED')

    def test_last_text_requires_reviewed_image(self):
        self.history['records'].append({'status': 'published', 'threads_post_id': '1', 'image_url': ''})
        self.assertEqual(bridge.next_media(self.history), 'IMAGE')

    def test_bad_schema_is_not_overwritten(self):
        self.queue['schema_version'] = 0
        with self.assertRaisesRegex(ValueError, 'QUEUE_SCHEMA'):
            self.check()


if __name__ == '__main__':
    unittest.main()
