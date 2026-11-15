import unittest
from threads_v4.publish_preflight import preflight
class PreflightTests(unittest.TestCase):
    def test_hold_cannot_publish(self):
        r=preflight({"notice_id":"a1","decision":"HOLD"},{"entries":[]},{"entries":[]},account="hid_119")
        self.assertEqual(r["status"],"BLOCKED")
        self.assertIn("OFFICIAL_REVIEW_NOT_PASS",r["blockers"])
    def test_wrong_account(self):
        r=preflight({"notice_id":"a1","decision":"HOLD"},{"entries":[]},{"entries":[]},account="other")
        self.assertIn("ACCOUNT_MISMATCH",r["blockers"])
if __name__=="__main__":unittest.main()
