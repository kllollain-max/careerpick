"""Delivery ledger must not confuse detection with delivery."""
import unittest
import tempfile
from pathlib import Path
from scripts.alert_delivery_ledger import delivered, mark_delivered, delivery_key, load, save

class DeliveryLedgerTests(unittest.TestCase):
    def test_only_explicit_delivery_is_recorded(self):
        initial = {"delivered": []}
        self.assertFalse(delivered(initial, "job1", "sub1"))
        updated = mark_delivered(initial, "job1", "sub1")
        self.assertFalse(delivered(initial, "job1", "sub1"))
        self.assertTrue(delivered(updated, "job1", "sub1"))
        self.assertEqual(updated["delivered"], [delivery_key("job1", "sub1")])
        self.assertNotIn("sub1", str(updated))
        self.assertFalse(delivered(updated, "job1", "sub2"))
        self.assertEqual(updated, mark_delivered(updated, "job1", "sub1"))

    def test_delivery_key_does_not_expose_subscription(self):
        key = delivery_key("job1", "private-device-id")
        self.assertEqual(len(key), 64)
        self.assertNotIn("private-device-id", key)
        self.assertNotEqual(key, delivery_key("job1", "another-device"))

    def test_atomic_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private" / "ledger.json"
            snapshot = mark_delivered({"delivered": []}, "job1", "sub1")
            save(path, snapshot)
            self.assertEqual(load(path), snapshot)
            self.assertNotIn("sub1", path.read_text(encoding="utf-8"))

    def test_preserves_metadata(self):
        initial = {"delivered": [], "version": 1, "source": "private"}
        updated = mark_delivered(initial, "job1", "sub1")
        self.assertEqual(updated["version"], 1)
        self.assertEqual(updated["source"], "private")
        self.assertEqual(initial["delivered"], [])

    def test_rejects_invalid_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text('{"delivered":"wrong"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load(path)

    def test_rejects_raw_or_malformed_delivery_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            for value in ("raw-subscription-id", 123, "A" * 64, "g" * 64):
                with self.subTest(value=value):
                    path.write_text('{"delivered": [' + __import__("json").dumps(value) + ']}',
                                    encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load(path)

    def test_missing_identity_rejected(self):
        with self.assertRaises(ValueError):
            mark_delivered({}, "", "sub1")

if __name__ == "__main__":
    unittest.main()
