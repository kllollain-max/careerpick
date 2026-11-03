import unittest
import unicodedata
from gojobs_notice_safety import classify_notice as check

ACTUAL_307403_TITLE = "2026년 제1회 대전광역시 중구의회 지방시간선택제임기제  공무원(나급) 채용시험 최종합격자 발표 및 임용후보자  임용 등록요령 공고"
VERIFIED_OPEN = {"official_text": "공식 모집요강 확인", "official_verified": True,
                 "application_open_verified": True}

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
        self.assertEqual(check("공무원 채용 공고",deadline="2026-11-01",as_of="2026-11-03"),
                         {"category": "상태 미확인", "recruiting": False, "reason": "deadline_elapsed_unverified"})
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

    def test_actual_id_307403_remains_results_despite_future_api_deadline(self):
        for flags in ({}, VERIFIED_OPEN):
            result = check(ACTUAL_307403_TITLE, as_of="2026-11-03", deadline="2026-11-13", **flags)
            self.assertEqual(result, {"category": "합격자 발표", "recruiting": False, "reason": "announcement_title"})
            self.assertEqual(set(result), {"category", "recruiting", "reason"})

    def test_cancellation_and_withdrawal_override_positive_open_flags(self):
        for title in ("공무원 채용공고 취소", "공무원 채용공고 철회", "모집공고 철회 안내"):
            with self.subTest(title=title):
                result = check(title, **VERIFIED_OPEN)
                self.assertEqual(result["category"], "취소 공고")
                self.assertFalse(result["recruiting"])
                self.assertEqual(result["reason"], "cancellation_title")

    def test_mixed_notices_are_held_even_with_positive_flags(self):
        titles = ("최종합격자 발표 및 미충원 인원 추가 모집 공고",
                  "채용공고 취소 및 재공고", "필기시험 장소 안내 및 원서접수 기간 연장",
                  "추가 모집 공고 및 최종합격자 발표", "채용 공고 및 합격자 발표",
                  "추가 모집 및 최종합격자 발표", "재공고 및 기존 채용공고 취소",
                  "임용후보자 등록 안내 및 추가모집 공고",
                  "추가모집 최종합격자 발표 및 재공고")
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(check(title, **VERIFIED_OPEN), {
                    "category": "상태 미확인", "recruiting": False, "reason": "mixed_notice_signals"})

    def test_negated_cancellation_is_not_asserted_as_cancelled(self):
        for title in ("채용공고 취소 아님", "채용공고 취소가 아님", "채용공고 취소되지 않음", "채용공고 취소 없음",
                      "운전면허 취소자 교육 강사 채용 공고"):
            result = check(title, **VERIFIED_OPEN)
            self.assertEqual(result["category"], "상태 미확인")
            self.assertEqual(result["reason"], "ambiguous_cancellation_title")
            self.assertFalse(result["recruiting"])

    def test_unicode_normalization_keeps_adversarial_notice_signals(self):
        cases = [("２０２６년 공무원 채용공고 취\u200b소", "취소 공고"),
                 ("공무원\u00a0채용공고\u2060철\ufeff회", "취소 공고"),
                 ("최종\u200b합 격 자\u2009발표", "합격자 발표"),
                 (unicodedata.normalize("NFD", "최종합격자 발표"), "합격자 발표"),
                 ("필기\u3000시험\u00a0장소\u2060안내", "시험 안내")]
        for title, category in cases:
            with self.subTest(category=category):
                result = check(title, **VERIFIED_OPEN)
                self.assertEqual(result["category"], category)
                self.assertFalse(result["recruiting"])
        self.assertEqual(check("채용 공고", official_text="\u200b\ufeff", official_verified=True,
                               application_open_verified=True)["reason"], "missing_official_text")

    def test_regular_schedule_mentions_preserve_verified_recruitment_path(self):
        bodies = ("합격자 발표일: 2026-12-10\n원서접수 마감일: 2026-11-30",
                  "접수 마감 후 합격자 발표", "최종합격자 발표 예정일: 2026-12-10",
                  "합격자 발표: 2026.12.10(예정)", "합격자 발표일정은 별도 안내",
                  "합격자\u200b 발표일: 2026-12-10; 접수\u00a0마감일: 2026-11-30")
        for body in bodies:
            with self.subTest(body=body):
                result = check("공무원 채용 공고", official_text=body, official_verified=True,
                               application_open_verified=True)
                self.assertEqual(result, {"category": "모집공고", "recruiting": True,
                                          "reason": "official_open_verified"})
        self.assertTrue(check("서류전형 없는 채용 공고", **VERIFIED_OPEN)["recruiting"])

    def test_actual_official_result_and_closure_conflicts_are_still_held(self):
        for body in ("최종합격자 발표", "최종합격자를 다음과 같이 공고합니다", "최종합격자 명단",
                     "합격자 발표일: 2026-12-10; 최종합격자 발표"):
            with self.subTest(body=body):
                result = check("채용 공고", official_text=body, official_verified=True,
                               application_open_verified=True)
                self.assertEqual(result["reason"], "conflicting_official_announcement")
                self.assertFalse(result["recruiting"])
        for body, reason in (("접수가 마감되었습니다", "conflicting_official_closure"),
                             ("모집은 종료되었습니다", "conflicting_official_closure"),
                             ("접수를 마감했습니다", "conflicting_official_closure"),
                             ("채용공고를 철회합니다", "conflicting_official_cancellation")):
            result = check("채용 공고", official_text=body, official_verified=True, application_open_verified=True)
            self.assertEqual(result["reason"], reason)
            self.assertEqual(result["category"], "상태 미확인")

    def test_verification_flags_require_actual_bools_and_cannot_conflict(self):
        for field in ("official_verified", "application_open_verified", "application_closed_verified"):
            for value in ("True", 1, 0, None, [], {}):
                with self.subTest(field=field, value_type=type(value).__name__):
                    flags = {**VERIFIED_OPEN, field: value}
                    result = check("채용 공고", **flags)
                    self.assertEqual(result["reason"], "invalid_verification_flags")
                    self.assertFalse(result["recruiting"])
        result = check("채용 공고", **VERIFIED_OPEN, application_closed_verified=True)
        self.assertEqual(result["reason"], "conflicting_application_status")
        self.assertEqual(result["category"], "상태 미확인")

    def test_all_supplied_dates_are_validated_before_status_or_title_branches(self):
        for field in ("deadline", "as_of"):
            for value in ("2026-02-30", "2026-99-01", "20261103", "", True, 20261103):
                for title in ("채용 공고", ACTUAL_307403_TITLE):
                    with self.subTest(field=field, value=value, title_kind=title[:5]):
                        result = check(title, **VERIFIED_OPEN, **{field: value})
                        self.assertEqual(result["reason"], "invalid_date")
                        self.assertFalse(result["recruiting"])

    def test_api_dates_and_unverified_source_never_establish_official_status(self):
        for flags in ({}, {"official_text": "접수 중", "application_open_verified": True},
                      {"application_closed_verified": True}):
            result = check("채용 공고", deadline="2026-11-30", as_of="2026-11-03", **flags)
            self.assertEqual(result["category"], "상태 미확인")
            self.assertFalse(result["recruiting"])
        self.assertFalse(check("채용 공고", deadline="2026-11-30")["recruiting"])
        self.assertEqual(check("채용 공고", official_text="공식 원문 확인", official_verified=True,
                               deadline="2026-11-30", as_of="2026-11-03")["reason"], "application_status_unverified")
        # Explicit inspected current official status can supersede an old API date.
        self.assertTrue(check("채용 공고", **VERIFIED_OPEN, deadline="2026-11-01", as_of="2026-11-03")["recruiting"])
        self.assertEqual(check("채용 공고", official_text="공식 종료 확인", official_verified=True,
                               application_closed_verified=True, deadline="2026-11-30", as_of="2026-11-03")["category"], "접수 종료")

    def test_standalone_registration_and_result_exam_context_have_distinct_labels(self):
        for title in ("임용후보자 등록 안내", "임용후보자 임용 등록요령 공고", "최종합격자 등록 안내"):
            result = check(title)
            self.assertEqual(result["category"], "등록 안내")
            self.assertEqual(result["reason"], "candidate_registration_title")
        for title in ("공개경쟁채용시험 최종합격자 발표", "추가모집 최종합격자 발표"):
            self.assertEqual(check(title)["category"], "합격자 발표")
        self.assertEqual(check("공무원 면접 장소 안내")["category"], "시험 안내")
if __name__=="__main__":
    unittest.main()
