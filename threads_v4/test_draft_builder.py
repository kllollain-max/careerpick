import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from threads_v4.draft_builder import make_draft
NOW=datetime(2026,11,15,14,tzinfo=ZoneInfo("Asia/Seoul"))
def approved():
    return dict(notice_id="a1",institution_document_checked=True,correction_checked=True,
        application_window_checked=True,unit_headcount_checked=True,eligibility_checked=True,
        existing_post_checked=True,profile_checked=True,official_source_sha256="a"*64,
        application_deadline_at="2026-11-20T18:00:00+09:00",
        official_checked_at="2026-11-15T13:00:00+09:00",already_posted=False,
        organization="시험기관",position="행정직",employment="정규직",headcount=3,
        eligibility="학사학위 소지자",official_url="https://example.org/notice")
class DraftBuilderTests(unittest.TestCase):
    def test_valid_text(self):
        d=make_draft(approved(),"2026-11-15T16:00:00+09:00","TEXT",NOW)
        self.assertIn("정규직",d["post_text"])
        self.assertTrue(d["post_text"].endswith("자세한 사항은 프로필링크 확인"))
        self.assertEqual(d["approval_status"],"DRAFT_REQUIRES_QUEUE_REVIEW")
    def test_hold_rejected(self):
        e=approved();e["institution_document_checked"]=False
        with self.assertRaisesRegex(ValueError,"OFFICIAL_EVIDENCE_NOT_APPROVED"):
            make_draft(e,"2026-11-15T16:00:00+09:00","TEXT",NOW)
    def test_image_needs_review(self):
        with self.assertRaises(ValueError):
            make_draft(approved(),"2026-11-15T16:00:00+09:00","IMAGE",NOW)
    def test_image_reviewed(self):
        e=approved();e["card_review_passed"]=True
        self.assertEqual(make_draft(e,"2026-11-15T16:00:00+09:00","IMAGE",NOW)["media"],"IMAGE")
    def test_missing_position(self):
        e=approved();e.pop("position")
        with self.assertRaises(ValueError):
            make_draft(e,"2026-11-15T16:00:00+09:00","TEXT",NOW)
if __name__=="__main__":unittest.main()
