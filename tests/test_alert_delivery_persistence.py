"""Regression checks for private, persistent alert delivery records."""
import tempfile
import unittest
from pathlib import Path

from scripts.alert_delivery_ledger import (
    delivery_key, delivered, load, mark_delivered, save,
)


class AlertDeliveryPersistenceTests(unittest.TestCase):
    def test_round_trip_and_no_raw_subscription_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.json"
            self.assertEqual(load(path), {"delivered": []})
            state = mark_delivered(load(path), "job-1", "private-subscription-123")
            save(path, state)
            self.assertTrue(delivered(load(path), "job-1", "private-subscription-123"))
            self.assertNotIn("private-subscription-123", path.read_text())
            self.assertEqual(len(load(path)["delivered"]), 1)

    def test_idempotent_mark(self):
        state = mark_delivered({"delivered": []}, "job-1", "sub-1")
        state = mark_delivered(state, "job-1", "sub-1")
        self.assertEqual(len(state["delivered"]), 1)

    def test_different_alert_kinds_are_separate(self):
        state = mark_delivered({"delivered": []}, "job-1", "sub-1", "new_job")
        self.assertFalse(delivered(state, "job-1", "sub-1", "deadline_d1"))
        self.assertNotEqual(delivery_key("job-1", "sub-1", "new_job"),
                            delivery_key("job-1", "sub-1", "deadline_d1"))

    def test_corrupt_ledger_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.json"
            path.write_text('{"delivered": ["raw-id"]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load(path)


if __name__ == "__main__":
    unittest.main()
