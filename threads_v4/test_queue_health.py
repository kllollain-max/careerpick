import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from threads_v4.queue_health import inspect

NOW = datetime(2026, 11, 15, 13, 30, tzinfo=ZoneInfo("Asia/Seoul"))
def entry(nid, slot, status="ready"):
    return {"notice_id": nid, "scheduled_at": slot, "writer": {"status": status}}
class QueueHealthTests(unittest.TestCase):
    def test_empty_supply(self):
        r = inspect({"schema_version": 1, "entries": []}, {"schema_version": 1, "entries": []}, {"records": [], "posted_ids": []}, NOW)
        self.assertEqual(r["status"], "SUPPLY_REQUIRED")
        self.assertIn("2026-11-15T16:00:00+09:00", r["missing_slots"])
    def test_past_only(self):
        r = inspect({"schema_version": 1, "entries": [entry("a1", "2026-11-14T08:00:00+09:00")]}, {"schema_version": 1, "entries": []}, {"records": [], "posted_ids": []}, NOW)
        self.assertEqual(r["ready_count"], 0)
    def test_duplicate_post(self):
        r = inspect({"schema_version": 1, "entries": [entry("a1", "2026-11-15T16:00:00+09:00")]}, {"schema_version": 1, "entries": []}, {"records": [], "posted_ids": ["a1"]}, NOW)
        self.assertTrue(r["duplicates"])
    def test_ready_flag_without_copy_is_not_ready(self):
        q={"schema_version":1,"entries":[{"notice_id":"a1","scheduled_at":"2026-11-15T16:00:00+09:00","writer":{"status":"ready"}}]}
        r=inspect(q,{"schema_version":1,"entries":[]},{"records":[],"posted_ids":[]},NOW)
        self.assertEqual(r["ready_count"],0)
    def test_missing_independent_review_is_not_ready(self):
        q={"schema_version":1,"entries":[{"notice_id":"a1","scheduled_at":"2026-11-15T16:00:00+09:00","writer":{"status":"ready","post_text":"원고"}}]}
        r=inspect(q,{"schema_version":1,"entries":[]},{"records":[],"posted_ids":[]},NOW)
        self.assertEqual(r["ready_count"],0)
        self.assertEqual(r["invalid"][0]["reason"],"INDEPENDENT_REVIEW_MISSING")
    def test_unreviewed(self):
        r = inspect({"schema_version": 1, "entries": [entry("a1", "2026-11-15T16:00:00+09:00", "draft")]}, {"schema_version": 1, "entries": []}, {"records": [], "posted_ids": []}, NOW)
        self.assertTrue(r["invalid"])
if __name__ == "__main__":
    unittest.main()
