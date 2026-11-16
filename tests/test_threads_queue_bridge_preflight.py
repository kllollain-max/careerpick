"""Regression tests for reviewed supply promotion. No GitHub or Meta writes."""
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts.threads_queue_bridge import merge, future_slots, ready_future_slots, supply_status, verified_supply_status


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
