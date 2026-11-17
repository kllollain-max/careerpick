"""Regression tests for reviewed supply promotion. No GitHub or Meta writes."""
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts.threads_queue_bridge import merge, future_slots, ready_future_slots, supply_status, verified_supply_status


class PendingActiveMediaTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 18, 8, 5, tzinfo=ZoneInfo("Asia/Seoul"))
        self.history = {"posted_ids": [], "records": [
            {"status": "published", "threads_post_id": "last", "image_url": "image"}]}
        self.entries = [{"notice_id": str(hour),
            "scheduled_at": f"2026-11-18T{hour:02d}:00:00+09:00",
            "prepared_at": "2026-11-17T20:00:00+09:00", "writer": {"status": "ready"}}
            for hour in [8, 12, 16, 20]]

    def verify(self, entry, *args, expected_media=None, **kwargs):
        if expected_media == "IMAGE" and entry["notice_id"] in ["8", "16"]:
            raise ValueError("CARD_VISUAL_REVIEW_REQUIRED")
        return {}

    @patch("scripts.threads_queue_bridge.verify_entry")
    def test_active_unstarted_text_keeps_following_media_forecast(self, verify):
        from scripts.threads_queue_bridge import media_for_slot
        verify.side_effect = self.verify
        status = verified_supply_status(self.entries, self.now, self.history, {}, {}, {})
        self.assertEqual(status["approved_inventory_count"], 3)
        self.assertFalse(status["invalid_ready_entries"])
        self.assertEqual(status["pending_active_slots"], [self.entries[0]["scheduled_at"]])
        self.assertTrue(status["media_forecast_conditional_on_active_slot"])
        self.assertEqual(media_for_slot(self.history, self.entries, self.entries[2]["scheduled_at"], self.now, {}, {}, {}), "TEXT")

    @patch("scripts.threads_queue_bridge.verify_entry")
    def test_stale_active_does_not_consume_media(self, verify):
        def check(entry, *args, **kwargs):
            if entry["notice_id"] == "8": raise ValueError("SOURCE_STALE")
            return self.verify(entry, *args, **kwargs)
        verify.side_effect = check
        status = verified_supply_status(self.entries, self.now, self.history, {}, {}, {})
        self.assertEqual(status["pending_active_slots"], [])
        self.assertIn({"notice_id": "16", "slot": self.entries[2]["scheduled_at"], "reason": "CARD_VISUAL_REVIEW_REQUIRED"}, status["invalid_ready_entries"])

    @patch("scripts.threads_queue_bridge.verify_entry")
    def test_confirmed_active_is_not_counted_twice(self, verify):
        verify.side_effect = self.verify
        self.history["records"].append({"scheduled_at": self.entries[0]["scheduled_at"], "status": "published", "threads_post_id": "new", "image_url": None})
        self.history["posted_ids"].append("8")
        status = verified_supply_status(self.entries, self.now, self.history, {}, {}, {})
        self.assertFalse(status["pending_active_slots"])
        self.assertFalse(status["invalid_ready_entries"])

    @patch("scripts.threads_queue_bridge.verify_entry", return_value={})
    def test_draft_expired_and_started_active_never_consume_media(self, verify):
        from scripts.threads_queue_bridge import pending_active_slot
        self.assertFalse(pending_active_slot(self.entries[0], self.now.replace(hour=10), self.history))
        self.history["records"].append({"scheduled_at": self.entries[0]["scheduled_at"], "status": "pending"})
        self.assertFalse(pending_active_slot(self.entries[0], self.now, self.history))
        self.entries[0]["writer"]["status"] = "draft"
        status = verified_supply_status(self.entries, self.now, self.history, {}, {}, {})
        self.assertFalse(status["pending_active_slots"])
        self.assertNotIn("8", [c.args[0]["notice_id"] for c in verify.call_args_list])


class ThreadsQueueBridgeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        self.slot = "2026-11-16T12:00:00+09:00"
        self.entry = {
            "notice_id": "verified-unique-1",
            "scheduled_at": self.slot,
            "writer": {"status": "ready"},
        }
        self.queue = {"schema_version": 1, "entries": []}
        self.stage = {"schema_version": 1, "entries": [self.entry]}
        self.history = {"records": [], "posted_ids": []}

    def test_future_slot_is_eligible_for_preflight(self):
        self.assertIn(self.slot, future_slots(self.now))

    @patch("scripts.threads_queue_bridge.verify_entry", return_value={})
    def test_promoted_entry_fills_missing_slot(self, _verify):
        merged, approved, refused = merge(
            self.queue, self.stage, self.history, {}, {}, {}, self.now
        )
        self.assertEqual(len(approved), 1)
        self.assertFalse(refused)
        self.assertNotIn(
            self.slot,
            [slot for slot in future_slots(self.now)
             if slot not in {e.get("scheduled_at") for e in merged["entries"]}],
        )

    def test_unapproved_entry_does_not_fill_slot(self):
        unapproved = {**self.entry, "writer": {"status": "draft"}}
        self.assertNotIn(self.slot, ready_future_slots([unapproved], self.now))
        self.assertIn(self.slot, ready_future_slots([self.entry], self.now))

    def test_next_slot_missing_flag(self):
        self.assertTrue(supply_status([], self.now)['next_slot_missing'])
        self.assertFalse(supply_status([self.entry], self.now)['next_slot_missing'])
        self.assertTrue(supply_status([self.entry], self.now)['missing_slots'])

    @patch("scripts.threads_queue_bridge.verify_entry", side_effect=ValueError("SOURCE_STALE"))
    def test_ready_but_stale_entry_is_reported_missing(self, _verify):
        status = verified_supply_status([self.entry], self.now, self.history, {}, {}, {})
        self.assertIn(self.slot, status["missing_slots"])
        self.assertNotIn(self.slot, status["approved_future_slots"])
        self.assertEqual(status["invalid_ready_entries"][0]["reason"], "SOURCE_STALE")
        self.assertTrue(status["next_slot_missing"])

    @patch("scripts.threads_queue_bridge.verify_entry", return_value={})
    def test_validated_entry_is_reported_ready(self, _verify):
        status = verified_supply_status([self.entry], self.now, self.history, {}, {}, {})
        self.assertIn(self.slot, status["approved_future_slots"])
        self.assertNotIn(self.slot, status["missing_slots"])
        self.assertFalse(status["invalid_ready_entries"])

    @patch("scripts.threads_queue_bridge.verify_entry", return_value={})
    def test_duplicate_slot_not_promoted(self, _verify):
        queue = {"schema_version": 1, "entries": [self.entry]}
        merged, approved, refused = merge(
            queue, self.stage, self.history, {}, {}, {}, self.now
        )
        self.assertEqual(len(merged["entries"]), 1)
        self.assertFalse(approved)
        self.assertEqual(refused[0]["reason"], "SLOT_ALREADY_OCCUPIED")

    @patch("scripts.threads_queue_bridge.verify_entry", return_value={})
    def test_duplicate_staging_same_slot_promotes_only_once(self, _verify):
        duplicate = {**self.entry, "notice_id": "verified-unique-2"}
        stage = {"schema_version": 1, "entries": [self.entry, duplicate]}
        merged, approved, refused = merge(
            self.queue, stage, self.history, {}, {}, {}, self.now
        )
        self.assertEqual(len(approved), 1)
        self.assertEqual(len(merged["entries"]), 1)
        self.assertEqual(refused[0]["reason"], "SLOT_ALREADY_OCCUPIED")

    @patch("scripts.threads_queue_bridge.verify_entry", return_value={})
    def test_duplicate_staging_notice_across_slots_promotes_only_once(self, _verify):
        duplicate = {**self.entry, "scheduled_at": "2026-11-16T16:00:00+09:00"}
        stage = {"schema_version": 1, "entries": [self.entry, duplicate]}
        merged, approved, refused = merge(
            self.queue, stage, self.history, {}, {}, {}, self.now
        )
        self.assertEqual(len(approved), 1)
        self.assertEqual(len(merged["entries"]), 1)
        self.assertEqual(refused[0]["reason"], "DUPLICATE_QUEUE_NOTICE")

    def test_malformed_queue_entry_fails_closed(self):
        queue = {"schema_version": 1, "entries": [None]}
        with self.assertRaisesRegex(ValueError, "QUEUE_ENTRY_SCHEMA"):
            merge(queue, self.stage, self.history, {}, {}, {}, self.now)

    def test_malformed_staging_entry_fails_closed(self):
        stage = {"schema_version": 1, "entries": [None]}
        with self.assertRaisesRegex(ValueError, "STAGING_ENTRY_SCHEMA"):
            merge(self.queue, stage, self.history, {}, {}, {}, self.now)

    def test_malformed_history_fails_closed(self):
        history = {"records": "invalid", "posted_ids": []}
        with self.assertRaisesRegex(ValueError, "HISTORY_SCHEMA"):
            merge(self.queue, self.stage, history, {}, {}, {}, self.now)

    @patch("scripts.threads_queue_bridge.verify_entry", return_value={})
    def test_claimed_slot_not_promoted(self, _verify):
        _, approved, refused = merge(
            self.queue, self.stage, self.history, {}, {}, {}, self.now,
            claimed_slots={self.slot},
        )
        self.assertFalse(approved)
        self.assertEqual(refused[0]["reason"], "SLOT_ALREADY_CLAIMED")


if __name__ == "__main__":
    unittest.main()
