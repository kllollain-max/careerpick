"""Offline multi-run persistence and crash quarantine for private push queue."""
import unittest
from scripts.private_push_delivery_queue import (
    empty_queue, enqueue, transition, quarantine_inflight, counts)
from scripts.alert_delivery_ledger import delivery_key


class PrivateQueueTests(unittest.TestCase):
    def pairs(self, n, jobs=66):
        return [({"id": "a%d" % j}, {"subscription_id": "synthetic-%d" % i})
                for i in range(n) for j in range(jobs)]

    def test_1000_subscribers_66_jobs_over_many_runs(self):
        pairs = self.pairs(1000)
        state = empty_queue()
        ledger = {"delivered": [], "pending": []}
        for offset in range(0, 1000, 100):
            state = enqueue(state, pairs[offset * 66:(offset + 100) * 66], ledger)
        self.assertEqual(counts(state)["pending"], 66000)
        keys = sorted(state["tasks"])
        for offset in range(0, 12, 3):
            for key in keys[offset:offset + 3]:
                state = transition(state, key, "reserved")
                state = transition(state, key, "accepted", message_id="mock-%s" % key[:8])
        self.assertEqual(counts(state)["accepted"], 12)
        self.assertEqual(counts(state)["pending"], 65988)
        self.assertEqual(counts(state)["total"], 66000)

    def test_crash_reservations_never_auto_retry(self):
        state = enqueue(empty_queue(), self.pairs(1, 3), {"delivered": [], "pending": []})
        key = delivery_key("a0", "synthetic-0")
        state = transition(state, key, "reserved")
        state = quarantine_inflight(state)
        self.assertEqual(counts(state)["uncertain"], 1)
        with self.assertRaises(ValueError):
            transition(state, key, "reserved")

    def test_existing_ledger_and_new_jobs(self):
        old = self.pairs(1, 1)
        key = delivery_key("a0", "synthetic-0")
        state = enqueue(empty_queue(), old, {"delivered": [], "pending": [key]})
        self.assertEqual(counts(state)["uncertain"], 1)
        state = enqueue(state, self.pairs(2, 2), {"delivered": [], "pending": []})
        self.assertEqual(counts(state)["total"], 4)
        self.assertEqual(counts(state)["uncertain"], 1)

    def test_invalid_transitions_and_message_id(self):
        state = enqueue(empty_queue(), self.pairs(1, 1), {"delivered": [], "pending": []})
        key = next(iter(state["tasks"]))
        with self.assertRaises(ValueError):
            transition(state, key, "accepted", message_id="mock")
        state = transition(state, key, "reserved")
        with self.assertRaises(ValueError):
            transition(state, key, "accepted")
