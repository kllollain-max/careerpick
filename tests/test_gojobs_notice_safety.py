import unittest
from gojobs_notice_safety import classify_notice as check

class NoticeSafetyTests(unittest.TestCase):
    def test_final_result_future_deadline(self):
        r=check("2026년 지방시간선택제임기제 공무원 최종합격자 발표 및 임용후보자 등록 안내",deadline="2026-11-13",as_of="2026-11-03")
        self.assertEqual(r["category"],"합격자 발표")
        self.assertFalse(r["recruiting"])
    def test_exam(self):
        self.assertEqual(check("공무원 필기시험 장소 안내")["category"],"시험 안내")
    def test_deadline_is_not_open_proof(self):
        self.assertEqual(check("공무원 채용 공고",deadline="2026-11-30",as_of="2026-11-03")["category"],"상태 미확인")
    def test_verified_closed(self):
        self.assertEqual(check("공무원 채용 공고",official_text="접수 마감",official_verified=True)["category"],"접수 종료")
    def test_elapsed(self):
        self.assertEqual(check("공무원 채용 공고",deadline="2026-11-01",as_of="2026-11-03")["category"],"접수 종료")
    def test_missing_source(self):
        self.assertFalse(check("공무원 채용 공고",application_open_verified=True)["recruiting"])
    def test_confirmed_open(self):
        self.assertTrue(check("공무원 채용 공고",official_text="공식 모집요강 확인",official_verified=True,application_open_verified=True)["recruiting"])
    def test_conflict_blocks(self):
        self.assertFalse(check("공무원 채용 공고",official_text="최종합격자 발표",official_verified=True,application_open_verified=True)["recruiting"])
    def test_unknown(self):
        self.assertEqual(check("기관 안내")["category"],"상태 미확인")
    def test_invalid_date(self):
        self.assertFalse(check("채용 공고",deadline="2026-99-99",as_of="2026-11-03")["recruiting"])
    def test_no_implicit_web_verification(self):
        self.assertFalse(check("채용 공고",official_text="접수 중",application_open_verified=True)["recruiting"])
if __name__=="__main__":
    unittest.main()
