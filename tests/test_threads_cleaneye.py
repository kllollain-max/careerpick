"""Synthetic source and publication-boundary fixtures; no network or real posts."""

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import threads_auto as publisher
from scripts import threads_writer_input as writer_input
from scripts.cleaneye_source_adapter import (
    KST, SourceValidationError, eligible_cleaneye_post, is_recruitment_notice,
    validate_cleaneye_feed, validate_cleaneye_post,
)
from scripts.threads_writer_queue import CTA, QueueValidationError, fingerprint, select_ready, validate_entry
from tests import test_threads_writer_queue as alio_fixtures


NOW = datetime(2026, 11, 6, 11, 20, tzinfo=KST)


def cleaneye_post(identity="00700", *, title="정보보안 담당자 일반정규직 채용", count="3"):
    url = "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=" + identity
    detail = {
        "공고 고유번호": identity, "기관명": "예시연구원", "채용제목": title,
        "공식 공고 URL": url, "고용형태 원문": "일반정규직", "채용인원": count,
        "채용상태 원문": "모집중", "접수개시일 원문": "2026-11-01", "접수마감일 원문": "2026-11-18",
        "기관 시도명": "서울특별시", "기관주소": "서울특별시 기관주소",
        "직위": "정보보안 담당자", "직무세부내용": "정보보안 시스템 관리 업무",
        "자격증1": "정보보안 기사", "지역제한": "N", "근무지": "null",
    }
    return {
        "id": "cleaneye-" + identity, "type": "j", "cleaneye": True, "source": "클린아이 잡플러스",
        "org": detail["기관명"], "title": title, "url": url, "src": url, "pub": None,
        "start": "2026-11-01", "due": "2026-11-18T23:59:59+09:00", "dueHasTime": False,
        "emp": ["일반정규직"], "n": int(count) if count.isdigit() else None,
        "region": "", "sourceRegion": "서울특별시", "sourceStatus": "모집중",
        "receptionState": "verified_open", "sourceMissing": False, "cleaneyeDetail": detail,
    }


def feed(*posts):
    return {"source": "cleaneye", "collectionStatus": "verified", "updated": "2026-11-06T10:00:00+09:00",
            "last_received": sum(p["sourceMissing"] is False for p in posts), "posts": list(posts)}


class CleaneyeSourceTests(unittest.TestCase):
    def setUp(self):
        self.post = cleaneye_post()
        self.feed = feed(self.post)

    def test_source_mapping_preserves_id_dates_conditions_and_unknown_workplace(self):
        before = deepcopy(self.feed)
        facts = validate_cleaneye_post(self.post, self.feed, NOW)
        self.assertEqual(facts["official_id"], "00700")
        self.assertEqual(facts["source"], "cleaneye")
        self.assertEqual(facts["employment"], "일반정규직")
        self.assertEqual(facts["count"], 3)
        self.assertEqual(facts["location"], "")
        self.assertEqual(facts["institution_region"], "서울특별시")
        self.assertEqual(facts["requirements"]["자격증1"], "정보보안 기사")
        self.assertEqual(facts["application_period"], {
            "start": "2026-11-01", "end": "2026-11-18", "start_date_only": True, "date_only": True})
        self.assertEqual(self.feed, before)
        for value in ("", "null", "미정", "2명(예비 1명)"):
            self.post["cleaneyeDetail"]["채용인원"] = value
            self.assertIsNone(validate_cleaneye_post(self.post, self.feed, NOW)["count"])

    def test_empty_duplicate_malformed_or_inconsistent_feed_cannot_initialize_a_baseline(self):
        bad = [feed(), feed(self.post, deepcopy(self.post))]
        changed = deepcopy(self.post)
        changed["id"] = "cleaneye-other"
        bad.append(feed(changed))
        bad.extend({**self.feed, "last_received": value} for value in (True, -1, 0, 2, "1"))
        for candidate in bad:
            with self.subTest(candidate=candidate):
                with self.assertRaises(SourceValidationError):
                    validate_cleaneye_feed(candidate, NOW)
        self.post["receptionState"] = "expired"
        self.assertTrue(validate_cleaneye_feed(self.feed, NOW))
        self.assertFalse(eligible_cleaneye_post(self.post, self.feed, NOW))

    def test_future_stale_unverified_or_naive_feed_is_not_eligible(self):
        for changes in ({"source": "alio"}, {"collectionStatus": "not_collected"},
                        {"updated": "2026-11-05T10:00:00+09:00"},
                        {"updated": "2026-11-06T12:00:00+09:00"},
                        {"updated": "2026-11-06T10:00:00"}):
            self.assertFalse(eligible_cleaneye_post(self.post, {**self.feed, **changes}, NOW))
        with self.assertRaisesRegex(SourceValidationError, "CLEANEYE_SOURCE_STALE"):
            validate_cleaneye_post(self.post, self.feed, NOW, scheduled=NOW + timedelta(days=1))

    def test_review_missing_source_and_non_open_states_are_excluded(self):
        for changes in ({"receptionState": "upcoming"}, {"receptionState": "verification_pending"},
                        {"receptionState": "invalid_date"}, {"receptionState": "cancelled"},
                        {"sourceMissing": True}, {"deadlineReviewReason": "far_future_source_date"}):
            candidate = {**self.post, **changes}
            self.assertFalse(eligible_cleaneye_post(candidate, feed(candidate), NOW))
        self.post["cleaneyeDetail"]["채용상태 원문"] = "마감"
        self.assertFalse(eligible_cleaneye_post(self.post, self.feed, NOW))

    def test_actual_short_opening_titles_use_source_purpose_but_exam_results_never_do(self):
        cases = [
            ("GX 프로그램 강사(명상) 위촉공고(변경)", {}),
            ("공고2026-82호 내과 전문의", {"구직자한마디": "본원 홈페이지 채용공고 참조"}),
            ("공고2025-83호 간호직 7급 간호사(3교대)", {"구직자한마디": "본원 홈페이지 채용공고 필수 참조"}),
            ("공고2026-70호 기술직 8급 의공기사", {"구직자한마디": "본원 홈페이지 채용공고 참조"}),
            ("공고2026-70호 기간제 미화원", {"구직자한마디": "본원 홈페이지 채용공고 필히 참조!!"}),
            ("병원 원무과 조리원(정규직) 재공고", {"직위": "조리원", "직무세부내용": "조리원업무"}),
        ]
        for title, fields in cases:
            post = cleaneye_post(title=title)
            post["cleaneyeDetail"].update(fields)
            self.assertTrue(eligible_cleaneye_post(post, feed(post), NOW), title)
        for title in ("통합채용 필기시험 안내", "직원 채용 면접전형 일정 공고", "채용 최종 합격자 공고",
                      "직원 모집 결과 발표", "신규직원 채용 취소 공고", "채용시험 장소 안내"):
            post = cleaneye_post(title=title)
            post["cleaneyeDetail"]["구직자한마디"] = "본원 채용공고 참조"
            self.assertFalse(is_recruitment_notice(title, post["cleaneyeDetail"]))
            self.assertFalse(eligible_cleaneye_post(post, feed(post), NOW))
        post = cleaneye_post(title="주간 운영 안내")
        with self.assertRaisesRegex(SourceValidationError, "CLEANEYE_RECRUITMENT_PURPOSE_UNCONFIRMED"):
            validate_cleaneye_post(post, feed(post), NOW)

    def test_raw_date_precision_wins_over_normalized_end_of_day(self):
        self.post["due"] = "2026-11-06T23:59:59+09:00"
        self.post["cleaneyeDetail"]["접수마감일 원문"] = "2026-11-06"
        self.assertFalse(eligible_cleaneye_post(self.post, self.feed, NOW))
        self.post["dueHasTime"] = True
        self.assertFalse(eligible_cleaneye_post(self.post, self.feed, NOW))
        self.post["cleaneyeDetail"]["접수마감일 원문"] = "2026-11-06 12:00"
        self.post["due"] = "2026-11-06T12:00:00+09:00"
        self.assertTrue(eligible_cleaneye_post(self.post, self.feed, NOW))
        self.assertFalse(eligible_cleaneye_post(self.post, self.feed, NOW.replace(hour=12, minute=0)))
        self.post["start"] = self.post["cleaneyeDetail"]["접수개시일 원문"] = "2026-11-06"
        self.assertFalse(eligible_cleaneye_post(self.post, self.feed, NOW))

    def test_official_url_identity_and_source_date_conflicts_fail_closed(self):
        for url in ("https://job.cleaneye.go.kr.evil.test/user/ypCareersData.do?idx=00700",
                    "https://job.cleaneye.go.kr/user/ypCareersData.do?idx=00701",
                    "http://job.cleaneye.go.kr/user/ypCareersData.do?idx=00700",
                    "https://user@job.cleaneye.go.kr/user/ypCareersData.do?idx=00700"):
            self.assertFalse(eligible_cleaneye_post({**self.post, "url": url}, self.feed, NOW))
        self.post["due"] = "2026-11-19T23:59:59+09:00"
        self.assertFalse(eligible_cleaneye_post(self.post, self.feed, NOW))


class CleaneyeWriterTests(unittest.TestCase):
    def setUp(self):
        self.alio = alio_fixtures.WriterQueueTests()
        self.alio.setUp()
        self.now, self.slot = self.alio.now, self.alio.slot
        self.post = cleaneye_post()
        self.feed = feed(self.post)
        self.source = {**self.alio.source, "_cleaneye": self.feed}
        self.entry = deepcopy(self.alio.entry)
        self.entry.update(notice_id=self.post["id"], source="cleaneye", official_id="00700")
        self.entry["writer"]["post_text"] = (
            "정보보안 자격을 갖춘 분을 위한 채용이에요.\n\n예시연구원에서 정보보안 담당자를 모집해요.\n"
            "인원: 3명\n고용형태: 일반정규직\n근무지: 서울\n정보보안 기사 자격이 필요해요.\n"
            "접수 마감일은 2026년 11월 18일이에요.\n\n" + CTA)
        review = self.entry["writer"]["review"]
        review["notice_id"] = self.post["id"]
        evidence = "접수기간: 2026-11-01 ~ 2026-11-18"
        source_ref = "cleaneye.json#" + self.post["id"]
        review["source_refs"] = [
            {"ref": source_ref, "checked_at": review["checked_at"], "excerpt": evidence},
            {"url": self.post["url"], "checked_at": review["checked_at"], "excerpt": "근무지: 서울. 정보보안 기사 필수."},
        ]
        review["fact_evidence"] = [{"field": "location", "value": "서울", "source_ref": self.post["url"],
                                    "excerpt": "근무지: 서울"}]
        review["application_period"] = {"start": "2026-11-01", "end": "2026-11-18", "start_date_only": True,
                                        "date_only": True, "source_ref": source_ref, "evidence": evidence}
        review["profile_target"].update(notice_id=self.post["id"],
            notice_url="https://kllollain-max.github.io/careerpick/jobs/cleaneye-00700.html")
        self.entry["image_job"].update(id=self.post["id"], title=self.post["title"],
                                      employment="일반정규직", deadline_label="2026-11-18")
        self.refresh()

    def refresh(self):
        self.entry["source_post_sha256"] = fingerprint(self.post)
        self.entry["source_detail_sha256"] = fingerprint(self.post["cleaneyeDetail"])

    def validate(self):
        return validate_entry(self.entry, self.slot, self.now, self.alio.history,
                              self.source, self.alio.details, self.alio.policy)

    def test_cleaneye_can_be_selected_as_one_reviewed_master_post(self):
        before = deepcopy((self.source, self.entry, self.alio.history))
        result = select_ready({"schema_version": 1, "entries": [self.entry]}, self.slot,
                              self.slot + timedelta(minutes=5), self.alio.history,
                              self.source, self.alio.details, self.alio.policy)
        self.assertEqual((result["source"], result["official_id"], result["job_id"]),
                         ("cleaneye", "00700", "cleaneye-00700"))
        self.assertEqual(result["image_job"]["deadline_label"], "2026-11-18")
        self.assertEqual(result["reply_text"], "")
        self.assertEqual(result["engagement_text"], "")
        self.assertEqual((self.source, self.entry, self.alio.history), before)
        # The old ALIO entry and its fingerprint contract remain valid unchanged.
        self.alio.validate()

    def test_identity_raw_edit_and_missing_or_stale_feed_invalidate_ready_copy(self):
        self.entry["official_id"] = "700"
        with self.assertRaisesRegex(QueueValidationError, "CLEANEYE_ENTRY_IDENTITY"):
            self.validate()
        self.entry["official_id"] = "00700"
        self.post["cleaneyeDetail"]["자격증1"] += " 및 경력 2년"
        with self.assertRaisesRegex(QueueValidationError, "SOURCE_CHANGED"):
            self.validate()
        self.refresh()
        self.feed["updated"] = "2026-11-05T10:00:00+09:00"
        with self.assertRaisesRegex(QueueValidationError, "CLEANEYE_SOURCE_STALE"):
            self.validate()

    def test_institution_region_is_never_accepted_as_workplace_evidence(self):
        review = self.entry["writer"]["review"]
        review["source_refs"][1]["excerpt"] = "기관 시도명: 서울특별시, 기관주소: 서울"
        review["fact_evidence"][0]["excerpt"] = "기관주소: 서울"
        with self.assertRaisesRegex(QueueValidationError, "IMAGE_LOCATION_UNSUPPORTED"):
            self.validate()
        review["source_refs"][1]["excerpt"] = "근무지 미상. 기관주소: 서울"
        review["fact_evidence"][0]["excerpt"] = review["source_refs"][1]["excerpt"]
        with self.assertRaisesRegex(QueueValidationError, "IMAGE_LOCATION_UNSUPPORTED"):
            self.validate()
        review["fact_evidence"] = None
        with self.assertRaisesRegex(QueueValidationError, "IMAGE_LOCATION_UNSUPPORTED"):
            self.validate()

    def test_date_only_source_cannot_be_relabelled_as_a_2359_closing_time(self):
        review = self.entry["writer"]["review"]
        review["application_period"].update(end="2026-11-18T23:59:00+09:00", date_only=False)
        review["application_period"]["evidence"] += " 23:59"
        review["source_refs"][0]["excerpt"] = review["application_period"]["evidence"]
        with self.assertRaisesRegex(QueueValidationError, "CLEANEYE_APPLICATION_PRECISION_CONFLICT"):
            self.validate()

    def test_source_change_and_history_are_rechecked_before_any_send(self):
        history = deepcopy(self.alio.history)
        env = {"THREADS_SCHEDULE_CRON": "0 3 * * *", "THREADS_MANUAL_PUBLISH": "false", "GITHUB_RUN_ATTEMPT": "1"}
        queue = {"schema_version": 1, "entries": [self.entry]}
        inputs = (self.alio.policy, self.source, self.alio.details)
        with patch.dict(os.environ, env), patch.object(publisher, "writer_inputs", return_value=inputs), \
                patch.object(publisher, "load", return_value=queue), patch.object(publisher, "save"), \
                patch.object(publisher, "create_media") as send:
            publisher.prepare_master(history, self.slot + timedelta(minutes=5), "880")
            self.assertEqual(len(history["records"]), 1)
            record = history["records"][0]
            publisher.validate_master_before_send(record, history, self.slot + timedelta(minutes=6))
            self.post["receptionState"] = "verification_pending"
            with self.assertRaisesRegex(QueueValidationError, "CLEANEYE_NOT_VERIFIED_OPEN"):
                publisher.validate_master_before_send(record, history, self.slot + timedelta(minutes=7))
            send.assert_not_called()

    def test_new_source_keeps_alternating_images_daily_cap_and_notice_deduplication(self):
        self.entry["writer"]["review"]["repetition_check"] = "checked"
        for prior_image, expected in (("", True), ("https://prior/image.jpg", False)):
            history = {"posted_ids": ["a699"], "records": [{"job_id": "a699", "status": "published",
                "threads_post_id": "1", "image_url": prior_image, "reserved_date": "2026-11-05", "text": "이전 공고"}]}
            with patch.dict(os.environ, {"THREADS_SCHEDULE_CRON": "0 3 * * *", "THREADS_MANUAL_PUBLISH": "false", "GITHUB_RUN_ATTEMPT": "1"}), \
                    patch.object(publisher, "writer_inputs", return_value=(self.alio.policy, self.source, self.alio.details)), \
                    patch.object(publisher, "load", return_value={"schema_version": 1, "entries": [self.entry]}), \
                    patch.object(publisher, "save"):
                publisher.prepare_master(history, self.slot + timedelta(minutes=5), "880")
                self.assertEqual(bool(history["records"][-1]["image_url"]), expected)
        self.alio.history["posted_ids"] = [self.post["id"]]
        with self.assertRaisesRegex(QueueValidationError, "NOTICE_ALREADY_USED"):
            self.validate()
        history = {"posted_ids": [], "records": [{"status": "published", "threads_post_id": str(i),
                    "reserved_date": self.slot.date().isoformat()} for i in range(4)]}
        with patch.dict(os.environ, {"THREADS_SCHEDULE_CRON": "0 3 * * *", "THREADS_MANUAL_PUBLISH": "false", "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(publisher, "writer_inputs") as inputs, patch.object(publisher, "save") as save:
            publisher.prepare_master(history, self.slot + timedelta(minutes=5), "881")
            inputs.assert_not_called()
            save.assert_not_called()
        self.assertEqual(len(history["records"]), 4)


class CleaneyeWriterInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.alio = alio_fixtures.WriterQueueTests()
        self.alio.setUp()
        self.alio.post.update(url="https://job.alio.go.kr/recruitview.do?idx=700", due="2026-11-18T23:59:00+09:00")
        self.prompt = (writer_input.ROOT / "threads/prompts/master-v1.1.txt").read_bytes()
        self.policy = deepcopy(self.alio.policy)
        self.policy["prompt_sha256"] = hashlib.sha256(self.prompt).hexdigest()
        self.write("threads/writer-policy.json", self.policy)
        (self.root / self.policy["prompt_path"]).parent.mkdir(parents=True, exist_ok=True)
        (self.root / self.policy["prompt_path"]).write_bytes(self.prompt)
        self.write("alio.json", self.alio.source)
        self.write("alio-detail.json", self.alio.details)
        self.write("operations-status.json", self.alio.source["_operations"])
        self.write("threads_posted.json", self.alio.history)

    def write(self, name, payload):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def build(self, limit=24):
        with patch.object(writer_input, "ROOT", self.root):
            return writer_input.build_input(NOW, limit)

    def test_actual_writer_input_mixes_sources_with_one_cap_and_no_queue_writes(self):
        posts = [cleaneye_post(str(800 + i), count="30") for i in range(40)]
        self.write("cleaneye.json", feed(*posts))
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.build()
        self.assertEqual(len(result["candidates"]), 24)
        self.assertEqual(len(result["slots"]), 4)
        self.assertEqual(result["master_prompt"].encode(), self.prompt)
        first = result["candidates"][0]
        self.assertEqual(first["source"], "cleaneye")
        self.assertEqual(first["notice_id"], "cleaneye-800")
        self.assertEqual(first["source_context"]["location"], "")
        self.assertEqual(first["source_context"]["application_period"]["end"], "2026-11-18")
        self.assertEqual(first["source_detail_sha256"], fingerprint(posts[0]["cleaneyeDetail"]))
        self.assertIn("a700", [p["notice_id"] for p in self.build(60)["candidates"]])
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_unknown_headcount_and_workplace_are_kept_and_prior_history_is_not_requeued(self):
        posts = [cleaneye_post("800", count=""), cleaneye_post("801"), cleaneye_post("802")]
        self.write("cleaneye.json", feed(*posts))
        self.write("threads_posted.json", {"posted_ids": ["cleaneye-801"], "records": [{"job_ids": ["cleaneye-802"]}]})
        result = self.build()
        self.assertEqual({p["notice_id"] for p in result["candidates"]}, {"a700", "cleaneye-800"})
        context = next(p["source_context"] for p in result["candidates"] if p.get("source") == "cleaneye")
        self.assertIsNone(context["count"])
        self.assertEqual(context["location"], "")

    def test_stale_or_unavailable_cleaneye_does_not_replace_existing_alio_input(self):
        stale = feed(cleaneye_post())
        stale["updated"] = "2026-11-05T10:00:00+09:00"
        self.write("cleaneye.json", stale)
        self.assertEqual([p["notice_id"] for p in self.build()["candidates"]], ["a700"])
        (self.root / "cleaneye.json").write_text("invalid JSON")
        self.assertEqual([p["notice_id"] for p in self.build()["candidates"]], ["a700"])
        for limit in (0, 61, True):
            with self.assertRaises(ValueError):
                self.build(limit)

    def test_input_hashes_and_current_policy_flow_through_check_queue_and_pre_send(self):
        fixture = CleaneyeWriterTests()
        fixture.setUp()
        self.write("cleaneye.json", fixture.feed)
        candidate = next(p for p in self.build()["candidates"] if p.get("source") == "cleaneye")
        entry = deepcopy(fixture.entry)
        for key in ("notice_id", "source", "official_id", "source_post_sha256", "source_detail_sha256"):
            entry[key] = candidate[key]
        entry["prompt_sha256"] = self.policy["prompt_sha256"]
        self.write(".threads-writer-queue.json", {"schema_version": 1, "entries": [entry]})
        with patch.object(writer_input, "ROOT", self.root):
            checked = writer_input.check_queue(self.root / ".threads-writer-queue.json", NOW)
        self.assertEqual([item["notice_id"] for item in checked["ready_entries"]], ["cleaneye-00700"])
        history = {"records": [], "posted_ids": []}
        with patch.object(publisher, "ROOT", self.root), patch.object(publisher, "DATA", self.root / "alio.json"), \
                patch.dict(os.environ, {"THREADS_SCHEDULE_CRON": "0 3 * * *", "THREADS_MANUAL_PUBLISH": "false", "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(publisher, "save") as save, patch.object(publisher, "create_media") as send:
            publisher.prepare_master(history, fixture.slot + timedelta(minutes=5), "880")
            self.assertEqual(len(history["records"]), 1)
            self.assertEqual(history["records"][0]["source"], "cleaneye")
            publisher.validate_master_before_send(history["records"][0], history, fixture.slot + timedelta(minutes=6))
            save.assert_called_once()
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
