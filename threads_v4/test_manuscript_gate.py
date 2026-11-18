import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from threads_v4.manuscript_gate import validate_copy, ReviewBlocked, CTA

NOW = datetime(2026, 11, 15, 13, tzinfo=ZoneInfo("Asia/Seoul"))
def good():
    return dict(post_text="기관 채용 공고를 확인하세요.\n"+CTA, reply_texts=[],
                official_verified=True, correction_checked=True, profile_verified=True,
                notice_id="a123", organization="기관", headcount=2, employment="정규직",
                eligibility="공식 요건", official_url="https://example.org", source_sha256="a"*64,
                scheduled_at="2026-11-15T16:00:00+09:00", deadline_at="2026-11-20T18:00:00+09:00",
                checked_at="2026-11-15T12:00:00+09:00", media="TEXT")
class GateTests(unittest.TestCase):
    def test_valid(self): self.assertTrue(validate_copy(good(), NOW))
    def test_no_official_review(self):
        x=good();x["official_verified"]=False
        with self.assertRaises(ReviewBlocked):validate_copy(x,NOW)
    def test_closed(self):
        x=good();x["deadline_at"]="2026-11-15T15:00:00+09:00"
        with self.assertRaises(ReviewBlocked):validate_copy(x,NOW)
    def test_image_requires_review(self):
        x=good();x["media"]="IMAGE"
        with self.assertRaises(ReviewBlocked):validate_copy(x,NOW)
    def test_url_forbidden(self):
        x=good();x["post_text"]="https://example.org\n"+CTA
        with self.assertRaises(ReviewBlocked):validate_copy(x,NOW)
    def test_duplicate_cta(self):
        x=good();x["post_text"]=CTA+"\n"+CTA
        with self.assertRaises(ReviewBlocked):validate_copy(x,NOW)
    def test_no_replies(self):
        x=good();x["reply_texts"]=["reply"]
        with self.assertRaises(ReviewBlocked):validate_copy(x,NOW)
    def test_old_slot(self):
        x=good();x["scheduled_at"]="2026-11-15T12:00:00+09:00"
        with self.assertRaises(ReviewBlocked):validate_copy(x,NOW)
if __name__=="__main__":unittest.main()
