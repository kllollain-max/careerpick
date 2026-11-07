"""Offline Cleaneye candidate/backlog/matching tests. No sends or API calls."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
import unittest

from scripts.alert_candidate_backlog import MAX_AGE, reconcile
from scripts.alert_delivery_ledger import delivery_key
from scripts.alert_preference_matcher import matches
from scripts.alert_source_contract import CLEANEYE_JOB_FIELDS, candidate_open, supported_job_id
from scripts.cleaneye_source_adapter import KST, eligible_cleaneye_post
from scripts.rollout_batch_planner import eligible_pairs


NOW = datetime(2026, 11, 7, 14, 0, tzinfo=KST)


def cleaneye(identifier="101", *, title="행정직 채용", start="2026-11-01",
             due="2026-11-12", emp=None, region="서울"):
    """Synthetic source-shaped record, never published as job data."""
    url = "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=" + identifier
    employment = ["일반정규직"] if emp is None else emp
    has_time = "T" in due or " " in due
    return {
        "id": "cleaneye-" + identifier, "type": "j", "cleaneye": True,
        "source": "클린아이 잡플러스", "sourceUpdated": "2026-11-07T13:00:00+09:00",
        "title": title, "org": "테스트 기관",
        "url": url, "src": url, "start": start,
        "due": due if has_time else due + "T23:59:59+09:00", "dueHasTime": has_time,
        "receptionState": "verified_open", "sourceStatus": "모집중", "sourceMissing": False,
        "sourceRegion": "부산", "region": region, "emp": employment, "edu": [],
        "cat": "지방공공기관 채용", "desc": "행정 업무", "text": "행정 업무 원문", "n": "2명",
        "cleaneyeDetail": {
            "공고 고유번호": identifier, "공식 공고 URL": url,
            "채용제목": title, "기관명": "테스트 기관", "채용상태 원문": "모집중",
            "접수개시일 원문": start, "접수마감일 원문": due,
            "고용형태 원문": " / ".join(employment), "근무지": region,
            "기관 시도명": "부산", "채용인원": "2명", "제출서류": "원문 제출서류",
        },
    }


def tags(**changes):
    profile = {"v": 4, "region": [], "employment": [], "education": [], "category": [],
               "keywords": "채용", **changes}
    return {"cp_optin": "yes", "cp_profile": json.dumps(profile, ensure_ascii=False)}


class CleaneyeCandidateTests(unittest.TestCase):
    def test_only_canonical_ids_are_supported_without_rewriting(self):
        for value in ("a1", "a0001", "cleaneye-101", "cleaneye-000101"):
            self.assertTrue(supported_job_id(value), value)
        for value in (None, 1, True, "", "a", "anew", "a1-extra", " a1", "a1\n",
                      "cleaneye-", "cleaneye-TEST_42", "cleaneye-101/x", "cleaneye-１０１"):
            self.assertFalse(supported_job_id(value), value)

    def test_source_shaped_open_candidate_and_existing_alio_deadline_rule(self):
        self.assertTrue(candidate_open(cleaneye(), NOW))
        self.assertTrue(candidate_open({"id": "a1", "title": "채용", "due": "2026-11-08"}, NOW))
        self.assertFalse(candidate_open({"id": "a1", "title": "채용", "due": "2026-11-07"}, NOW))
        self.assertFalse(candidate_open({"id": "a1", "title": "채용", "due": "2026-11-08", "cleaneye": True}, NOW))
        with self.assertRaises(ValueError):
            candidate_open(cleaneye(), NOW.replace(tzinfo=None))

    def test_unknown_same_day_cutoff_is_not_a_synthetic_2359_deadline(self):
        job = cleaneye(due="2026-11-07")
        self.assertFalse(candidate_open(job, NOW))
        job["dueHasTime"] = True  # A normalized 23:59 timestamp is not original evidence.
        self.assertFalse(candidate_open(job, NOW))
        exact = cleaneye(due="2026-11-07T15:00:00+09:00")
        self.assertTrue(candidate_open(exact, NOW))
        self.assertFalse(candidate_open(exact, NOW + timedelta(hours=1)))
        self.assertFalse(candidate_open(cleaneye(start="2026-11-07"), NOW))
        self.assertTrue(candidate_open(cleaneye(start="2026-11-07T14:00:00+09:00"), NOW))

    def test_pending_closed_missing_and_nonrecruitment_records_are_excluded(self):
        for state in ("verification_pending", "upcoming", "invalid_date", "source_error", "expired", "cancelled"):
            self.assertFalse(candidate_open({**cleaneye(), "receptionState": state}, NOW), state)
        for value in (True, None, "false"):
            self.assertFalse(candidate_open({**cleaneye(), "sourceMissing": value}, NOW))
        for title in ("채용 최종합격자 발표", "채용 취소 공고", "채용 면접시험 일정 안내", "일반 공지사항"):
            self.assertFalse(candidate_open(cleaneye(title=title), NOW), title)
        self.assertFalse(candidate_open({**cleaneye(), "sourceStatus": "접수마감"}, NOW))
        self.assertFalse(candidate_open(cleaneye(due="2054-07-10"), NOW))
        self.assertFalse(candidate_open({**cleaneye(), "deadlineReviewReason": "far_future_source_date"}, NOW))

    def test_identity_original_date_and_official_url_must_agree(self):
        for changes in ({"id": "cleaneye-102"}, {"cleaneye": False}, {"type": "m"},
                        {"source": "other"}, {"title": "다른 채용"}, {"org": "다른 기관"},
                        {"start": "2026-11-02"}, {"due": "2026-11-13T23:59:59+09:00"},
                        {"src": None}, {"url": "https://example.invalid/job?idx=101"}):
            self.assertFalse(candidate_open({**cleaneye(), **changes}, NOW), changes)
        self.assertFalse(candidate_open(cleaneye(start="2026-11-13"), NOW))

    def test_official_detail_can_establish_an_opening_without_title_keyword(self):
        job = cleaneye(title="내과 전문의 공고", emp=["전문계약직"])
        job["cleaneyeDetail"].update({"직위": "내과 전문의", "직무세부내용": "내과 전문의 진료 업무"})
        feed = {"source": "cleaneye", "collectionStatus": "verified", "updated": NOW.isoformat(), "posts": [job]}
        self.assertTrue(candidate_open(job, NOW))
        self.assertTrue(eligible_cleaneye_post(job, feed, NOW))
        result = deepcopy(job)
        result["title"] = result["cleaneyeDetail"]["채용제목"] = "내과 전문의 최종합격자 공고"
        self.assertFalse(candidate_open(result, NOW))

    def test_fresh_source_adapter_remains_separate_and_required(self):
        job = cleaneye()
        feed = {"source": "cleaneye", "collectionStatus": "verified", "updated": NOW.isoformat(), "posts": [job]}
        self.assertTrue(candidate_open(job, NOW))
        self.assertTrue(eligible_cleaneye_post(job, feed, NOW))
        # Retained row metadata alone never proves the source is still fresh.
        stale = {**feed, "updated": (NOW - timedelta(days=2)).isoformat()}
        self.assertFalse(eligible_cleaneye_post(job, stale, NOW))
        self.assertTrue(candidate_open(job, NOW))


class CleaneyeBacklogTests(unittest.TestCase):
    def test_roundtrip_preserves_source_metadata_ids_and_first_seen(self):
        raw = cleaneye("000101")
        original = deepcopy(raw)
        first = reconcile([], [raw], now=NOW)
        self.assertEqual(raw, original)
        stored = first[0]["job"]
        for key in CLEANEYE_JOB_FIELDS:
            self.assertEqual(stored.get(key), raw.get(key), key)
        self.assertEqual(stored["id"], "cleaneye-000101")
        self.assertEqual(stored["due"], raw["due"])
        self.assertIsNot(stored["cleaneyeDetail"], raw["cleaneyeDetail"])
        second = reconcile(first, [], now=NOW + timedelta(hours=1))
        third = reconcile(second, [raw], now=NOW + timedelta(hours=2))
        self.assertEqual(third[0]["first_seen"], first[0]["first_seen"])
        self.assertEqual(third[0]["job"], stored)
        feed = {"source": "cleaneye", "collectionStatus": "verified", "updated": NOW.isoformat(), "posts": [stored]}
        self.assertTrue(eligible_cleaneye_post(stored, feed, NOW))

    def test_corrections_and_unknown_cutoffs_cannot_retain_an_older_open_row(self):
        first = reconcile([], [cleaneye()], now=NOW)
        pending = {**cleaneye(), "receptionState": "verification_pending"}
        self.assertEqual(reconcile(first, [pending], now=NOW), [])
        self.assertEqual(reconcile(first, [cleaneye(due="2026-11-07")], now=NOW), [])
        self.assertEqual(reconcile([], [pending, cleaneye(title="채용 결과 발표")], now=NOW), [])

    def test_existing_retention_and_age_rules_are_preserved(self):
        old = [{"first_seen": (NOW - MAX_AGE - timedelta(seconds=1)).isoformat(), "job": cleaneye()}]
        self.assertEqual(reconcile(old, [], now=NOW), [])
        self.assertEqual(len(reconcile(old, [], now=NOW, retain_job_ids=["cleaneye-101"])), 1)
        old[0]["job"]["receptionState"] = "cancelled"
        self.assertEqual(reconcile(old, [], now=NOW, retain_job_ids=["cleaneye-101"]), [])
        with self.assertRaises(ValueError):
            reconcile([{"first_seen": NOW.isoformat(), "job": {"id": "anew"}}], [], now=NOW)


class CleaneyePreferenceTests(unittest.TestCase):
    def test_exact_observed_aliases_preserve_original_employment(self):
        for raw, expected in (("일반정규직", "정규직"), ("일반계약직", "계약직"), ("전문계약직", "계약직")):
            job = cleaneye(emp=[raw])
            self.assertTrue(matches(job, tags(employment=[expected])))
            self.assertTrue(matches(job, tags(employment=[raw])))
            self.assertEqual(job["emp"], [raw])
            other = "계약직" if expected == "정규직" else "정규직"
            self.assertFalse(matches(job, tags(employment=[other])))
        for raw in ("비상임", "비일반정규직", "일반정규직 예정"):
            self.assertFalse(matches(cleaneye(emp=[raw]), tags(employment=["정규직"])))
        self.assertFalse(matches(cleaneye(emp=["비상임"]), tags(employment=["계약직", "비정규직"])))
        # Alias expansion is source-specific; existing ALIO matching is unchanged.
        self.assertFalse(matches({**cleaneye(emp=["일반정규직"]), "cleaneye": False}, tags(employment=["정규직"])))

    def test_missing_employment_and_education_are_not_inferred_from_title(self):
        job = cleaneye(title="학력무관 정규직 채용", emp=[])
        self.assertFalse(matches(job, tags(employment=["정규직"])))
        self.assertFalse(matches(job, tags(education=["학력무관"])))
        self.assertFalse(matches({**job, "emp": "일반정규직"}, tags(employment=["정규직"])))
        self.assertFalse(matches({**job, "emp": [None, "null"]}, tags(employment=["null"])))

    def test_workplace_never_falls_back_to_institution_region(self):
        for region in ("", "null", None):
            job = cleaneye(region=region)
            job["sourceRegion"] = "서울"
            job["cleaneyeDetail"]["기관 시도명"] = "서울"
            job["cleaneyeDetail"]["기관주소"] = "서울 주소"
            self.assertFalse(matches(job, tags(region=["서울"])))
        job = cleaneye(region="서울")
        self.assertTrue(matches(job, tags(region=["서울"])))
        self.assertFalse(matches(job, tags(region=["부산"])))
        self.assertFalse(matches(job, tags(region=["서울"], education=["학력무관"])))


class CleaneyePlannerTests(unittest.TestCase):
    def test_cap_order_optin_and_existing_ledger_hashes_remain_unchanged(self):
        jobs = [{"id": "a1", "title": "채용", "due": "2026-11-12"}, cleaneye("102"), cleaneye("101")]
        subscribers = [
            {"subscription_id": "synthetic-off", "opted_in": False, "tags": tags()},
            {"subscription_id": "synthetic-1", "opted_in": True, "tags": tags()},
            {"subscription_id": "synthetic-2", "opted_in": True, "tags": tags()},
        ]
        ledger = {"delivered": [], "pending": []}
        first = eligible_pairs(jobs, subscribers, ledger, NOW, 3)
        self.assertEqual([(j["id"], s["subscription_id"]) for j, s in first],
                         [("a1", "synthetic-1"), ("cleaneye-102", "synthetic-1"), ("cleaneye-101", "synthetic-1")])
        self.assertEqual(ledger, {"delivered": [], "pending": []})
        ledger = {"delivered": [delivery_key("a1", "synthetic-1")],
                  "pending": [delivery_key("cleaneye-102", "synthetic-1")]}
        before = deepcopy(ledger)
        second = eligible_pairs(jobs + [jobs[2]], subscribers, ledger, NOW, 3)
        self.assertEqual([(j["id"], s["subscription_id"]) for j, s in second],
                         [("cleaneye-101", "synthetic-1"), ("a1", "synthetic-2"), ("cleaneye-102", "synthetic-2")])
        self.assertEqual(ledger, before)

    def test_bad_ids_and_ineligible_source_records_never_form_pairs(self):
        sub = [{"subscription_id": "synthetic-1", "opted_in": True, "tags": tags()}]
        bad = [{**cleaneye(), "id": "cleaneye-101x"}, {**cleaneye(), "receptionState": "verification_pending"},
               cleaneye(due="2026-11-07"), cleaneye(title="채용 합격자 발표"),
               {"id": "anew", "title": "채용", "due": "2026-11-12"}]
        self.assertEqual(eligible_pairs(bad, sub, {"delivered": [], "pending": []}, NOW, 3), [])
        self.assertEqual(eligible_pairs([cleaneye()], [{**sub[0], "tags": {}}], {}, NOW, 3), [])
        # Leading zeros are identity, not a normalized form of another notice.
        ledger = {"delivered": [delivery_key("cleaneye-101", "synthetic-1")], "pending": []}
        pairs = eligible_pairs([cleaneye("000101")], sub, ledger, NOW, 3)
        self.assertEqual(pairs[0][0]["id"], "cleaneye-000101")


if __name__ == "__main__":
    unittest.main()
