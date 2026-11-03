"""Offline tests for fail-closed private delivery reservation semantics."""
import unittest
from unittest.mock import patch

from scripts import private_delivery_store as store
from scripts.alert_delivery_ledger import delivery_key


class PrivateReservationTests(unittest.TestCase):
    def setUp(self):
        self.state = {"delivered": []}
        self.version = 0

    def read(self):
        return dict(self.state), str(self.version)

    def write(self, state, sha):
        if sha != str(self.version):
            raise RuntimeError("Version conflict")
        self.state = dict(state)
        self.version += 1

    def test_reserve_blocks_second_attempt_and_finalize(self):
        with patch.object(store, "read_private_ledger", side_effect=self.read), patch.object(
                store, "write_private_ledger", side_effect=self.write):
            self.assertTrue(store.reserve_private_delivery("job", "sub"))
            self.assertFalse(store.reserve_private_delivery("job", "sub"))
            self.assertIn(delivery_key("job", "sub"), self.state["pending"])
            store.finalize_private_delivery("job", "sub")
            self.assertIn(delivery_key("job", "sub"), self.state["delivered"])
            self.assertFalse(store.reserve_private_delivery("job", "sub"))

    def test_uncertain_result_remains_pending(self):
        with patch.object(store, "read_private_ledger", side_effect=self.read), patch.object(
                store, "write_private_ledger", side_effect=self.write):
            self.assertTrue(store.reserve_private_delivery("job", "sub"))
            self.assertFalse(store.reserve_private_delivery("job", "sub"))
            self.assertNotIn(delivery_key("job", "sub"), self.state["delivered"])

    def test_missing_ledger_fails_closed(self):
        with patch.object(store, "read_private_ledger", return_value=({"delivered": []}, None)):
            with self.assertRaises(RuntimeError):
                store.reserve_private_delivery("job", "sub")


    def test_storage_write_error_stops_reservation(self):
        with patch.object(store, "read_private_ledger", return_value=({"delivered": []}, "sha")), patch.object(
                store, "write_private_ledger", side_effect=OSError("Storage unavailable")):
            with self.assertRaises(OSError):
                store.reserve_private_delivery("job", "sub")

    def test_finalize_requires_pending_reservation(self):
        with patch.object(store, "read_private_ledger", return_value=({"delivered": []}, "sha")):
            with self.assertRaises(RuntimeError):
                store.finalize_private_delivery("job", "sub")



if __name__ == "__main__":
    unittest.main()
