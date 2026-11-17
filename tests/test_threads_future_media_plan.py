"""Regression: future IMAGE/TEXT forecast follows verified earlier slots, not a stale global IMAGE state.

Read-only tests; no GitHub or Meta writes.
"""
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
from scripts import threads_queue_bridge as bridge


class FutureMediaPlanningTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 9, tzinfo=ZoneInfo("Asia/Seoul"))
        self.history = {
            "posted_ids": ["already_posted_08"],
            "records": [{
                "job_id": "already_posted_08",
                "scheduled_at": "2026-11-17T08:00:00+09:00",
                "status": "published",
                "threads_post_id": "test-only",
                "image_url": "",   # Real 08 post was TEXT; next slot must IMAGE.
            }],
        }
        self.slots = [
            self.entry("approved_12", 12),
            self.entry("approved_16_text", 16),
            self.entry("approved_20", 20),
        ]

    @staticmethod
    def entry(identifier, hour):
        return {
            "notice_id": identifier,
            "scheduled_at": f"2026-11-17T{hour:02}:00:00+09:00",
            "writer": {"status": "ready", "post_text": "verified"},
        }

    def test_all_three_valid_future_turns_alternate_after_real_text(self):
        seen = []
        def verify(entry, *_args, expected_media=None):
            seen.append((entry["notice_id"], expected_media))
            if entry["notice_id"] == "approved_16_text" and expected_media == "IMAGE":
                raise ValueError("CARD_VISUAL_REVIEW_REQUIRED")
            return {"job_id": entry["notice_id"]}
        with patch.object(bridge, "verify_entry", side_effect=verify):
            status = bridge.verified_supply_status(
                self.slots, self.now, self.history, {}, {}, {})
        self.assertEqual(seen, [("approved_12", "IMAGE"),
                                ("approved_16_text", "TEXT"),
                                ("approved_20", "IMAGE")])
        self.assertEqual(status["approved_inventory_count"], 3)
        self.assertFalse(status["invalid_ready_entries"])

    def test_missing_earlier_slot_does_not_invent_image_turn(self):
        def verify(entry, *_args, expected_media=None):
            if expected_media == "IMAGE":
                raise ValueError("CARD_VISUAL_REVIEW_REQUIRED")
        with patch.object(bridge, "verify_entry", side_effect=verify):
            status = bridge.verified_supply_status(
                [self.slots[1]], self.now, self.history, {}, {}, {})
        self.assertFalse(status["approved_future_slots"])
        self.assertEqual(status["invalid_ready_entries"][0]["reason"],
                         "CARD_VISUAL_REVIEW_REQUIRED")

    def test_invalid_preceding_approval_does_not_toggle_media(self):
        def verify(entry, *_args, expected_media=None):
            if entry["notice_id"] == "approved_12":
                raise ValueError("UNVERIFIED_PRIOR_IMAGE")
            if entry["notice_id"] == "approved_16_text" and expected_media == "IMAGE":
                raise ValueError("CARD_VISUAL_REVIEW_REQUIRED")
        with patch.object(bridge, "verify_entry", side_effect=verify):
            status = bridge.verified_supply_status(
                self.slots[:2], self.now, self.history, {}, {}, {})
        self.assertFalse(status["approved_future_slots"])
        self.assertEqual(len(status["invalid_ready_entries"]), 2)

    def test_merge_predicts_text_after_approved_earlier_image(self):
        queue = {"schema_version": 1, "entries": [self.slots[0]]}
        staged = {"schema_version": 1, "entries": [self.slots[1]]}
        seen = []
        def verify(entry, *_args, expected_media=None):
            seen.append((entry["notice_id"], expected_media))
            if entry["notice_id"] == "approved_16_text" and expected_media == "IMAGE":
                raise ValueError("CARD_VISUAL_REVIEW_REQUIRED")
        with patch.object(bridge, "verify_entry", side_effect=verify):
            _, accepted, refused = bridge.merge(
                queue, staged, self.history, {}, {}, {}, self.now)
        self.assertEqual([e["notice_id"] for e in accepted],
                         ["approved_16_text"])
        self.assertFalse(refused)
        self.assertEqual(seen, [("approved_12", "IMAGE"),
                                ("approved_16_text", "TEXT")])

    def test_unapproved_earlier_stage_never_advances_forecast(self):
        candidate = self.slots[1]
        previous = {**self.slots[0], "writer": {"status": "draft"}}
        planned = bridge.media_for_slot(self.history, [previous],
                                        candidate["scheduled_at"], self.now,
                                        {}, {}, {})
        self.assertEqual(planned, "IMAGE")


if __name__ == "__main__":
    unittest.main()
