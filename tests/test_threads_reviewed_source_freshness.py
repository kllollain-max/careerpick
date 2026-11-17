"""No-network regressions for reviewed drafts awaiting a fresh scheduled source."""
import copy
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts.threads_writer_queue import _fresh, QueueValidationError
from scripts import threads_queue_bridge as bridge


class ScheduledSourceFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 22, 5, tzinfo=ZoneInfo("Asia/Seoul"))
        self.slot = datetime(2026, 11, 18, 20, tzinfo=ZoneInfo("Asia/Seoul"))
        self.bound = timedelta(hours=24)

    def test_source_fresh_now_is_stale_at_next_evening_slot(self):
        source = "2026-11-17T19:19:34+09:00"
        self.assertLess(self.now - datetime.fromisoformat(source), self.bound)
        with self.assertRaisesRegex(QueueValidationError, "^SOURCE_STALE$"):
            _fresh(source, self.now, self.slot, "SOURCE_STALE", self.bound)

    def test_full_twenty_four_hours_is_allowed_but_one_second_more_is_not(self):
        source = "2026-11-17T20:00:00+09:00"
        self.assertEqual(_fresh(source, self.now, self.slot, "SOURCE_STALE", self.bound),
                         datetime.fromisoformat(source))
        with self.assertRaisesRegex(QueueValidationError, "^SOURCE_STALE$"):
            _fresh(source, self.now, self.slot + timedelta(seconds=1),
                   "SOURCE_STALE", self.bound)

    def test_reviewed_card_does_not_promote_hold_or_consume_media_turn(self):
        hold = {"notice_id": "a307141", "scheduled_at": self.slot.isoformat(),
                "writer": {"status": "hold", "post_text": None, "draft_text": "reviewed",
                           "review": {"v5": {"card_visual_review": {"status": "passed"}}}}}
        queue = {"schema_version": 1, "entries": []}
        staged = {"schema_version": 1, "entries": [hold]}
        history = {"posted_ids": [], "records": [
            {"status": "published", "threads_post_id": "confirmed",
             "image_url": "https://example.invalid/confirmed-image"}]}
        before = copy.deepcopy((queue, staged, history))
        with patch.object(bridge, "validate_entry") as validator:
            out, accepted, refused = bridge.merge(
                queue, staged, history, {}, {}, {}, self.now)
            media = bridge.media_for_slot(
                history, [hold], "2026-11-19T08:00:00+09:00",
                self.now, {}, {}, {})
        validator.assert_not_called()
        self.assertEqual(out, queue)
        self.assertFalse(accepted)
        self.assertEqual(refused, [{"notice_id": "a307141", "reason": "STAGED_NOT_READY"}])
        self.assertEqual(media, "TEXT")
        self.assertEqual((queue, staged, history), before)


if __name__ == "__main__":
    unittest.main()
