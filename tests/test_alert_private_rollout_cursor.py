"""Offline checkpoint tests, without private credentials or network writes."""
import unittest
from scripts.private_rollout_cursor import plan_window, fingerprint


class PushCursorTests(unittest.TestCase):
    def test_sizes_and_resume(self):
        for total in (2, 100, 101, 1000, 10000):
            with self.subTest(total=total):
                ids = ["synthetic-%05d" % i for i in range(total)]
                state = {"version": 1, "next_index": 0, "export_hash": ""}
                seen = []
                while True:
                    window, next_index, digest = plan_window(ids, state, 100)
                    self.assertLessEqual(len(window), 100)
                    seen.extend(window)
                    state = {"version": 1, "next_index": next_index,
                             "export_hash": digest}
                    if next_index == 0:
                        break
                self.assertEqual(seen, ids)

    def test_crash_before_persist_replays_same_window(self):
        ids = ["synthetic-%03d" % i for i in range(101)]
        state = {"version": 1, "next_index": 0, "export_hash": fingerprint(ids)}
        first = plan_window(ids, state, 100)
        replay = plan_window(ids, state, 100)
        self.assertEqual(first, replay)

    def test_export_change_resets_cursor_safely(self):
        old = ["synthetic-%03d" % i for i in range(101)]
        state = {"version": 1, "next_index": 100, "export_hash": fingerprint(old)}
        updated = old + ["synthetic-new"]
        window, next_index, _ = plan_window(updated, state, 100)
        self.assertEqual(window, updated[:100])
        self.assertEqual(next_index, 100)


if __name__ == "__main__":
    unittest.main()
