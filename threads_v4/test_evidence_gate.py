import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from threads_v4.evidence_gate import decision
NOW=datetime(2026,11,15,14,tzinfo=ZoneInfo("Asia/Seoul"))
def good():
    return dict(notice_id="a1",institution_document_checked=True,correction_checked=True,
                application_window_checked=True,unit_headcount_checked=True,eligibility_checked=True,
                existing_post_checked=True,profile_checked=True,official_source_sha256="a"*64,
                application_deadline_at="2026-11-20T18:00:00+09:00",
                official_checked_at="2026-11-15T13:00:00+09:00",already_posted=False)
class EvidenceTests(unittest.TestCase):
    def test_hold_without_evidence(self):
        self.assertEqual(decision({"notice_id":"a305734","decision":"HOLD"},NOW)["decision"],"HOLD")
    def test_pass_complete(self):
        self.assertEqual(decision(good(),NOW)["decision"],"PASS")
    def test_uncertain_history_hold(self):
        e=good();e["already_posted"]=None
        self.assertEqual(decision(e,NOW)["decision"],"HOLD")
    def test_cancelled_reject(self):
        e=good();e["cancelled"]=True
        self.assertEqual(decision(e,NOW)["decision"],"REJECT")
    def test_stale_hold(self):
        e=good();e["official_checked_at"]="2026-11-13T13:00:00+09:00"
        self.assertEqual(decision(e,NOW)["decision"],"HOLD")
if __name__=="__main__":unittest.main()
