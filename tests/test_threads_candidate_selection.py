"""Selection gates against false application windows, unit totals and caps."""
from copy import deepcopy
from datetime import datetime, timedelta
import unittest

from scripts.threads_candidate_selection import (
    alio_application_period, build_selection, employment_rank, exact_count,
)
from scripts.threads_writer_queue import fingerprint
from tests import test_threads_writer_queue as queue_fixtures
from tests.test_threads_cleaneye import cleaneye_post, feed


class CandidateSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = queue_fixtures.WriterQueueTests()
        self.fixture.setUp()
        self.fixture.post["url"] = "https://job.alio.go.kr/recruitview.do?idx=700"
        self.fixture.entry["source_post_sha256"] = fingerprint(self.fixture.post)
        self.source = self.fixture.source
        self.details = self.fixture.details
        self.now = self.fixture.now
        self.policy = self.fixture.policy
        self.history = self.fixture.history

    def build(self, **kwargs):
        return build_selection(self.source, self.details, self.history, self.policy, self.now, **kwargs)

    def test_unknown_and_placeholder_counts_never_become_zero(self):
        for raw in (None, 0, True, "0", "00", "00명", "약간 명", "약 10명", "10~20", "1,000명"):
            with self.subTest(raw=raw):
                self.assertIsNone(exact_count(raw))
        self.assertEqual(exact_count("24명"), 24)
        self.fixture.detail["recrutNope"] = "320"
        result = self.build()
        chosen = result["candidates"][0]["selection_context"]
        self.assertEqual(chosen["notice_total_count"], 320)
        self.assertIsNone(chosen["unit_count"])

    def test_published_end_never_supplies_application_period(self):
        self.fixture.detail["scrnprcdrMthdExpln"] = "서류전형 후 면접을 실시합니다."
        result = self.build()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["review_candidates"][0]["notice_id"], "a700")
        self.assertEqual(result["review_candidates"][0]["application_status"], "unconfirmed")
        self.assertEqual(result["selection_audit"]["sources"]["alio"]["review_required_count"], 1)

    def test_actual_period_can_be_outside_old_publication_window(self):
        # The publication endpoint is outside the old 5--20 day selection range.
        self.fixture.post["due"] = "2027-03-31T23:59:00+09:00"
        result = self.build()
        self.assertEqual([p["notice_id"] for p in result["candidates"]], ["a700"])
        period = result["candidates"][0]["selection_context"]["application_period"]
        self.assertEqual(period["end"], "2026-11-18T17:00:00+09:00")

    def test_unknown_same_day_deadline_is_excluded(self):
        self.fixture.detail["scrnprcdrMthdExpln"] = "접수기간: 2026.11.1. ~ 2026.11.6."
        result = self.build()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["selection_audit"]["rows"][0]["reasons"], ["APPLICATION_END_TIME_UNKNOWN"])

    def test_other_stage_submission_window_is_not_application_window(self):
        for heading in ('면접 접수기간', '증빙서류 접수기간', '이의신청 접수기간', '합격자 등록 접수기간'):
            with self.subTest(heading=heading):
                self.fixture.detail['scrnprcdrMthdExpln'] = heading + ': 2026.11.1. ~ 2026.11.18. 17:00'
                period, reason = alio_application_period(self.fixture.detail, self.now)
                self.assertIsNone(period)
                self.assertEqual(reason, 'APPLICATION_PERIOD_REVIEW_REQUIRED')

    def test_ambiguous_reception_period_is_review_required(self):
        self.fixture.detail["aplyQlfcCn"] += "\n접수기간: 2026.11.2. ~ 2026.11.19."
        period, reason = alio_application_period(self.fixture.detail, self.now)
        self.assertIsNone(period)
        self.assertEqual(reason, "APPLICATION_PERIOD_AMBIGUOUS")

    def test_entire_feed_is_ranked_before_writer_cap(self):
        posts = [cleaneye_post(str(800 + i), count="500") for i in range(40)]
        for post in posts[:-1]:
            post["cleaneyeDetail"]["고용형태 원문"] = "일반계약직"
        self.source["_cleaneye"] = feed(*posts)
        result = self.build(limit=1)
        self.assertEqual(result["selection_audit"]["total_scanned"], 41)
        self.assertEqual(result["selection_audit"]["eligible_before_limit"], 41)
        # A regular candidate at the end of the source survives pre-limit ranking.
        self.assertEqual(result["candidates"][0]["notice_id"], "cleaneye-839")
        self.assertEqual(result["selection_audit"]["sources"]["cleaneye"]["total_records"], 40)

    def test_mixed_intern_and_regular_is_not_regular_priority(self):
        self.assertEqual(employment_rank("정규직"), 0)
        self.assertEqual(employment_rank("일반정규직"), 0)
        self.assertGreater(employment_rank("정규직,청년인턴(채용형)"), employment_rank("무기계약직"))
        self.assertNotEqual(employment_rank("비정규직"), 0)
        self.assertNotEqual(employment_rank("무기계약직"), 0)

    def test_prepared_notice_and_exact_source_alias_cannot_consume_writer_limit(self):
        duplicate = cleaneye_post("800", title=self.fixture.post["title"])
        self.fixture.post["src"] = duplicate["url"]
        alternative = cleaneye_post("801", title="별도 일반직 채용")
        self.source["_cleaneye"] = feed(duplicate, alternative)
        entry = deepcopy(self.fixture.entry)
        # Stale evidence cannot grant eligibility, but it does not cancel a
        # reservation or let the writer assign the same notice twice.
        entry["source_post_sha256"] = "0" * 64
        result = self.build(limit=1, queued_entries=[entry])
        self.assertEqual([p["notice_id"] for p in result["candidates"]], ["cleaneye-801"])
        self.assertIn("a700", result["all_blocked_notice_ids"])
        reasons = {r["notice_id"]: r["reasons"] for r in result["selection_audit"]["rows"]}
        self.assertEqual(reasons["a700"], ["NOTICE_ALREADY_QUEUED"])
        self.assertEqual(reasons["cleaneye-800"], ["EXACT_CROSS_SOURCE_NOTICE_ALREADY_USED"])

    def test_hold_and_expired_ready_are_not_active_queue_reservations(self):
        for status, at in (("hold", self.now + timedelta(hours=1)),
                           ("ready", self.now - timedelta(hours=2))):
            with self.subTest(status=status, at=at):
                entry = deepcopy(self.fixture.entry)
                entry["writer"]["status"] = status
                entry["scheduled_at"] = at.isoformat()
                result = self.build(queued_entries=[entry])
                self.assertEqual([p["notice_id"] for p in result["candidates"]], ["a700"])

    def test_fresh_review_supplies_unit_count_but_stale_or_changed_does_not(self):
        entry = deepcopy(self.fixture.entry)
        review = entry["writer"]["review"]
        excerpt = self.fixture.post["title"] + ": 정보보안 담당자 3명 모집"
        review["source_refs"].append({"ref": "official-unit", "excerpt": excerpt, "checked_at": review["checked_at"]})
        review["fact_evidence"] = [
            {"field": "title", "value": entry["image_job"]["title"], "source_ref": "official-unit", "excerpt": excerpt},
            {"field": "count", "value": 3, "source_ref": "official-unit", "excerpt": excerpt},
        ]
        result = self.build(reviewed_entries=[entry])
        self.assertEqual(result["candidates"][0]["selection_context"]["unit_count"], 3)
        self.assertEqual(result["candidates"][0]["selection_context"]["application_status"], "reviewed_open")
        self.assertEqual(result["selection_audit"]["review_errors"], [])
        changed = deepcopy(entry)
        changed["source_post_sha256"] = "0" * 64
        result = self.build(reviewed_entries=[changed])
        self.assertIsNone(result["candidates"][0]["selection_context"]["unit_count"])
        self.assertEqual(result["selection_audit"]["review_errors"][0]["reason"], "SOURCE_CHANGED")
        review["checked_at"] = (self.now - timedelta(hours=25)).isoformat()
        result = self.build(reviewed_entries=[entry])
        self.assertIsNone(result["candidates"][0]["selection_context"]["unit_count"])
        self.assertEqual(result["selection_audit"]["review_errors"][0]["reason"], "REVIEW_SOURCE_STALE")

    def test_independent_title_and_count_evidence_does_not_mix_units(self):
        entry = deepcopy(self.fixture.entry)
        review = entry["writer"]["review"]
        title = entry["image_job"]["title"]
        review["source_refs"].append({"ref": "units", "excerpt": title + " 별도 모집. 다른 직무 3명", "checked_at": review["checked_at"]})
        review["fact_evidence"] = [
            {"field": "title", "value": title, "source_ref": "units", "excerpt": title},
            {"field": "count", "value": 3, "source_ref": "units", "excerpt": "다른 직무 3명"},
        ]
        result = self.build(reviewed_entries=[entry])
        self.assertIsNone(result["candidates"][0]["selection_context"]["unit_count"])

    def test_count_equal_to_notice_total_still_requires_unit_evidence(self):
        result = self.build(reviewed_entries=[self.fixture.entry])
        self.assertEqual(result["selection_audit"]["review_errors"], [])
        row = result["candidates"][0]["selection_context"]
        self.assertIsNone(row["unit_count"])
        self.assertEqual(row["notice_total_count"], 3)

    def test_exact_cross_source_identity_is_not_republished(self):
        old = cleaneye_post("800", title=self.fixture.post["title"])
        shared_url = old["url"]
        self.fixture.post["src"] = shared_url
        self.source["_cleaneye"] = feed(old)
        self.history["posted_ids"] = [old["id"]]
        result = self.build()
        self.assertEqual(result["candidates"], [])
        row = next(r for r in result["selection_audit"]["rows"] if r["notice_id"] == "a700")
        self.assertEqual(row["reasons"], ["EXACT_CROSS_SOURCE_NOTICE_ALREADY_USED"])
        # Same institution with a genuinely different job title is not collapsed.
        self.fixture.post["title"] = "정보보안 신입 담당자 정규직 채용"
        self.fixture.detail["recrutPbancTtl"] = self.fixture.post["title"]
        self.assertEqual([p["notice_id"] for p in self.build()["candidates"]], ["a700"])

    def test_source_failure_is_not_zero_eligible_success(self):
        self.source["_operations"]["last_success_at"] = (self.now - timedelta(hours=30)).isoformat()
        result = self.build()
        self.assertEqual(result["candidates"], [])
        summary = result["selection_audit"]["sources"]["alio"]
        self.assertNotEqual(summary["status"], "verified_snapshot")
        self.assertEqual(summary["total_records"], 1)
        self.assertEqual(summary["excluded_count"], 1)
        self.assertFalse(result["selection_audit"]["official_details_fully_reviewed"])

    def test_triage_does_not_mutate_any_source_or_history(self):
        before = deepcopy((self.source, self.details, self.history, self.policy))
        self.build()
        self.assertEqual((self.source, self.details, self.history, self.policy), before)


if __name__ == "__main__":
    unittest.main()
