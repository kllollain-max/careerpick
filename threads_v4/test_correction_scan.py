import unittest
from threads_v4.correction_scan import scan
class CorrectionTests(unittest.TestCase):
    def test_disqualification_not_cancel(self):
        r=scan("부정한 방법으로 채용된 사실이 적발되어 채용이 취소된 자")
        self.assertEqual(r["status"],"NO_MATCH_NOT_PROOF_OF_ABSENCE")
    def test_actual_notice_cancel(self):
        self.assertEqual(scan("본 채용 공고를 취소합니다")["status"],"CANCELLATION_SUSPECTED")
    def test_correction(self):
        self.assertEqual(scan("채용 공고 정정 안내")["status"],"CORRECTION_REVIEW_REQUIRED")
    def test_no_match_not_approved(self):
        self.assertFalse(scan("정상적인 채용 안내")["official_approved"])
if __name__=="__main__":unittest.main()
