import unittest
from threads_v4.hold_preview import preview
class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.a={"notice_id":"a1","source":"https://example.org","institution_notice":"https://example.org",
                "official_page_content_review":{"organization":"기관","title":"연구위원","employment":"정규직",
                    "headcount":10,"qualification":"박사학위","application_window_as_published":"2026.10.06 ~ 2026.11.30"},
                "cross_source_text_evidence":{"institution_page_body_confirmed":True,"approval":"HOLD"}}
    def test_hold_only(self):
        r=preview(self.a)
        self.assertFalse(r["queue_eligible"])
        self.assertFalse(r["approved"])
        self.assertTrue(r["post_text"].endswith("자세한 사항은 프로필링크 확인"))
    def test_unconfirmed_blocks(self):
        self.a["cross_source_text_evidence"]["institution_page_body_confirmed"]=False
        with self.assertRaises(ValueError):preview(self.a)
if __name__=="__main__":unittest.main()
