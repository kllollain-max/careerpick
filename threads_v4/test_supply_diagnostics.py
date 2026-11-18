import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from threads_v4.supply_diagnostics import supply_decision
NOW=datetime(2026,11,15,14,tzinfo=ZoneInfo("Asia/Seoul"))
def empty():return {"schema_version":1,"entries":[]}
class SupplyTests(unittest.TestCase):
    def test_no_approval_no_supply(self):
        r=supply_decision(empty(),empty(),{"records":[],"posted_ids":[]},{"results":[{"decision":"HOLD","reason":"OFFICIAL_REVIEW_REQUIRED"}]},NOW)
        self.assertEqual(r["action"],"REVERIFY_OFFICIAL_DOCUMENTS")
        self.assertFalse(r["meta_posted"])
    def test_reviewed_staging_routes_bridge(self):
        r=supply_decision(empty(),{"schema_version":1,"entries":[{"notice_id":"a1"}]},{"records":[],"posted_ids":[]},{"results":[]},NOW)
        self.assertEqual(r["action"],"REVIEW_STAGING_AND_RUN_EXISTING_CAS_BRIDGE")
    def test_pass_needs_draft(self):
        r=supply_decision(empty(),empty(),{"records":[],"posted_ids":[]},{"results":[{"decision":"PASS"}]},NOW)
        self.assertEqual(r["action"],"BUILD_DRAFTS_FROM_VERIFIED_PASS_ONLY")
if __name__=="__main__":unittest.main()
