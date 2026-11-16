"""No-network regressions for verified queue CAS feeder."""
import unittest
import base64
import hashlib
import io
import json
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import threads_queue_bridge as bridge


class LargeQueueReadTests(unittest.TestCase):
    def read_large(self, corrupt=False):
        # Actual >1MiB Unicode JSON response with omitted Contents payload.
        raw = json.dumps({'entries': ['검증된 원고' * 100_000]}, ensure_ascii=False).encode()
        sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        meta = {'sha': sha, 'size': len(raw), 'content': '', 'encoding': 'none',
                'download_url': 'https://untrusted.invalid/never-follow'}
        blob = {'sha': sha, 'size': len(raw), 'encoding': 'base64',
                'content': base64.b64encode(raw.replace(b'entries', b'changed') if corrupt else raw).decode()}
        with patch.object(bridge, 'request', return_value=meta), \
             patch.dict(bridge.os.environ, {'GITHUB_REPOSITORY': 'owner/repo'}), \
             patch.object(bridge.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(blob).encode())) as opened:
            value = bridge.read('threads/writer-queue.json', 'private-test-token')
            self.assertEqual(opened.call_args.args[0].full_url,
                             'https://api.github.com/repos/owner/repo/git/blobs/' + sha)
        return value, sha

    def test_large_unicode_queue_reads_exact_immutable_blob(self):
        (value, actual), expected = self.read_large()
        self.assertEqual(actual, expected)
        self.assertEqual(value['entries'], ['검증된 원고' * 100_000])

    def test_changed_blob_never_accepted(self):
        with self.assertRaisesRegex(ValueError, 'QUEUE_BLOB_CONTENT_MISMATCH'):
            self.read_large(corrupt=True)

    def test_oversized_metadata_rejected_without_network(self):
        with patch.object(bridge, 'request', return_value={'sha': 'a'*40, 'size': 20_000_001, 'content': ''}), \
             patch.object(bridge.urllib.request, 'urlopen') as opened:
            with self.assertRaisesRegex(ValueError, 'QUEUE_BLOB_METADATA_INVALID'):
                bridge.read('threads/writer-queue.json', 'private-test-token')
            opened.assert_not_called()


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


class DelayedReviewedBridgeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 16, 49, tzinfo=ZoneInfo('Asia/Seoul'))
        self.entry = {'notice_id': 'a306965', 'scheduled_at': '2026-11-15T16:00:00+09:00',
                      'prepared_at': '2026-11-15T14:02:00+09:00',
                      'writer': {'status': 'ready', 'post_text': 'verified'}}
        self.history = {'posted_ids': [], 'records': []}

    def test_delayed_preflight_preserves_existing_grace(self):
        self.assertTrue(bridge.eligible_staged_slot(self.entry, self.now))

    def test_newly_prepared_after_slot_is_rejected(self):
        self.entry['prepared_at'] = '2026-11-15T16:01:00+09:00'
        self.assertFalse(bridge.eligible_staged_slot(self.entry, self.now))

    def test_two_hour_boundary_is_closed(self):
        self.assertFalse(bridge.eligible_staged_slot(self.entry, self.now.replace(hour=18, minute=0)))

    def test_missing_or_naive_prepared_time_rejected(self):
        del self.entry['prepared_at']
        self.assertFalse(bridge.eligible_staged_slot(self.entry, self.now))
        self.entry['prepared_at'] = '2026-11-15T14:02:00'
        self.assertFalse(bridge.eligible_staged_slot(self.entry, self.now))

    def test_delayed_entry_still_runs_full_validator(self):
        with patch.object(bridge, 'validate_entry', side_effect=ValueError('SOURCE_CHANGED')) as validator:
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                bridge.verify_entry(self.entry, self.now, self.history, {}, {}, {})
            validator.assert_called_once()

    def test_other_notice_reservation_blocks_slot(self):
        self.history['records'] = [{'job_id': 'a111', 'scheduled_at': self.entry['scheduled_at'], 'status': 'pending'}]
        _, approved, refused = bridge.merge({'schema_version': 1, 'entries': []},
            {'schema_version': 1, 'entries': [self.entry]}, self.history, {}, {}, {}, self.now)
        self.assertFalse(approved)
        self.assertEqual(refused[0]['reason'], 'SLOT_ALREADY_STARTED')

    def test_remote_claim_blocks_even_without_history(self):
        _, approved, refused = bridge.merge({'schema_version': 1, 'entries': []},
            {'schema_version': 1, 'entries': [self.entry]}, self.history, {}, {}, {}, self.now,
            claimed_slots={self.entry['scheduled_at']})
        self.assertFalse(approved)
        self.assertEqual(refused[0]['reason'], 'SLOT_ALREADY_CLAIMED')


if __name__ == '__main__':
    unittest.main()
