"""Adverse cases for the AI-copy/publisher boundary; no credentials or network."""

from copy import deepcopy
from datetime import datetime, timedelta
import unittest

from scripts.threads_writer_queue import (
    CTA, KST, QueueValidationError, fingerprint, select_ready, validate_entry,
)


class WriterQueueTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 11, 20, tzinfo=KST)
        self.slot = self.now.replace(hour=12, minute=0)
        checked = "2026-11-06T10:05:00+09:00"
        self.policy = {
            "schema_version": 1,
            "prompt_path": "threads/prompts/master-v1.1.txt",
            "prompt_sha256": "a" * 64,
            "cta": CTA,
            "max_chars": 450,
            "max_source_age_hours": 24,
            "slots": [8, 12, 16, 20],
            "formats": {"08": "reader_story", "12": "key_facts", "16": "job_explainer", "20": "application_checklist"},
        }
        self.post = {
            "id": "a700", "org": "예시연구원", "title": "정보보안 담당자 정규직 채용",
            "due": "2026-11-30T23:59:00+09:00", "dueHasTime": False,
            "emp": ["정규직"], "n": "3", "region": "서울",
        }
        self.period_evidence = "응시원서 접수기간: 2026. 11. 1. ~ 2026. 11. 18. 17:00까지"
        self.detail = {
            "recrutPblntSn": "700", "instNm": self.post["org"],
            "recrutPbancTtl": self.post["title"], "hireTypeNmLst": "정규직",
            "recrutNope": "3", "workRgnNmLst": "서울", "ongoingYn": "Y",
            "aplyQlfcCn": "정보보안 기사 자격증 소지자 3명 모집",
            "scrnprcdrMthdExpln": self.period_evidence,
            "pbancBgngYmd": "20261020", "pbancEndYmd": "20261130", "decimalDay": "24",
        }
        self.source = {
            "updated": "2026-11-06T10:00:00+09:00", "posts": [self.post],
            "_operations": {
                "source": "alio", "snapshot_at": "2026-11-06T10:00:00+09:00",
                "last_success_at": "2026-11-06T10:02:00+09:00", "unconfirmed_ids": [],
            },
        }
        self.details = {"a700": self.detail}
        self.history = {"records": [], "posted_ids": []}
        self.entry = {
            "scheduled_at": self.slot.isoformat(), "format_id": "key_facts", "notice_id": "a700",
            "prompt_sha256": self.policy["prompt_sha256"],
            "source_post_sha256": fingerprint(self.post), "source_detail_sha256": fingerprint(self.detail),
            "writer": {
                "status": "ready", "post_text": "정보보안 자격을 갖춘 분을 위한 채용이에요.\n\n예시연구원에서 정보보안 담당자를 모집해요.\n인원: 3명\n고용형태: 정규직\n근무지: 서울\n정보보안 기사 자격이 필요해요.\n접수는 2026년 11월 18일 17시에 마감해요.\n\n" + CTA,
                "draft_text": None, "reply_texts": [],
                "review": {
                    "notice_id": "a700", "target_reader": "정보보안 기사 자격 소지자",
                    "central_message": "서울에서 정보보안 업무를 수행하는 정규직 모집", "pattern_id": "P8",
                    "scheduled_at": self.slot.isoformat(), "reference_at": self.now.isoformat(),
                    "verification_basis": "provided_verified_data", "source_refs": [{"ref": "alio-detail.json#a700", "checked_at": checked}],
                    "checked_at": checked, "missing_or_conflicting": [], "omitted_optional_facts": ["급여 미공개"],
                    "repetition_check": "no_history", "cta_check": "passed", "media_check": "not_supplied",
                    "length_check": "measured_within_limit", "pre_publish_checks": ["게시 직전 현재 접수 상태와 이미지 파일 확인"],
                    "application_period": {
                        "start": "2026-11-01", "start_date_only": True,
                        "end": "2026-11-18T17:00:00+09:00", "date_only": False,
                        "source_ref": "alio-detail.json#a700", "evidence": self.period_evidence,
                    },
                    "profile_target": {
                        "url": "https://kllollain-max.github.io/careerpick/",
                        "notice_url": "https://kllollain-max.github.io/careerpick/jobs/alio-700.html",
                        "notice_id": "a700", "checked_at": checked, "verified": True,
                    },
                },
            },
            "image_job": {
                "id": "a700", "org": "예시연구원", "title": self.post["title"],
                "count": 3, "due": "2026-11-18", "employment": "정규직", "location": "서울",
                "deadline_label": "2026-11-18 17:00",
            },
        }

    def validate(self, entry=None, now=None, slot=None):
        return validate_entry(
            self.entry if entry is None else entry, self.slot if slot is None else slot,
            self.now if now is None else now, self.history, self.source, self.details, self.policy,
        )

    def reject(self, reason, entry=None, now=None, slot=None):
        with self.assertRaisesRegex(QueueValidationError, "^" + reason + "$"):
            self.validate(entry=entry, now=now, slot=slot)

    def refresh_hashes(self):
        self.entry["source_post_sha256"] = fingerprint(self.post)
        self.entry["source_detail_sha256"] = fingerprint(self.detail)

    def test_ready_copy_preserves_single_post_and_review_without_mutation(self):
        before = deepcopy(self.entry)
        result = self.validate()
        self.assertEqual(result["text"], self.entry["writer"]["post_text"])
        self.assertEqual(result["content_type"], "master_job")
        self.assertEqual(result["reply_text"], "")
        self.assertEqual(result["engagement_text"], "")
        self.assertEqual(result["queue_entry_sha256"], fingerprint(self.entry))
        result["writer_review"]["source_refs"].clear()
        result["image_job"]["title"] = "changed"
        self.assertEqual(self.entry, before)

    def test_only_top_level_detail_countdown_is_excluded_from_fingerprint(self):
        self.detail["decimalDay"] = "23"
        self.validate()
        self.assertNotEqual(fingerprint({"decimalDay": "23"}), fingerprint({"decimalDay": "24"}))
        self.assertNotEqual(fingerprint({"recrutPblntSn": "700", "nested": {"decimalDay": "23"}}), fingerprint({"recrutPblntSn": "700", "nested": {"decimalDay": "24"}}))
        self.assertEqual(fingerprint({"b": 2, "a": "한글"}), fingerprint({"a": "한글", "b": 2}))
        with self.assertRaisesRegex(QueueValidationError, "NON_CANONICAL_INPUT"):
            fingerprint({"n": float("nan")})

    def test_source_edits_require_rewriting_and_revalidating_queue(self):
        self.detail["aplyQlfcCn"] += " 및 경력 2년"
        self.reject("SOURCE_CHANGED")
        self.refresh_hashes()
        self.post["n"] = "4"
        self.reject("SOURCE_CHANGED")

    def test_publication_end_is_never_substituted_for_application_deadline(self):
        self.assertEqual(self.validate()["image_job"]["due"], "2026-11-18")
        self.entry["image_job"]["due"] = "2026-11-30"
        self.reject("IMAGE_APPLICATION_DEADLINE_CONFLICT")

    def test_current_source_and_pairing_proof_are_required(self):
        for change, reason in [
            ({"unconfirmed_ids": ["a700"]}, "SOURCE_NOTICE_UNCONFIRMED"),
            ({"snapshot_at": "2026-11-06T09:00:00+09:00"}, "SOURCE_SNAPSHOT_MISMATCH"),
            ({"last_success_at": "2026-11-05T09:00:00+09:00"}, "SOURCE_STALE"),
            ({"last_success_at": "2026-11-06T12:01:00+09:00"}, "SOURCE_STALE"),
        ]:
            original = deepcopy(self.source["_operations"])
            self.source["_operations"].update(change)
            with self.subTest(change=change):
                self.reject(reason)
            self.source["_operations"] = original
        del self.source["_operations"]
        self.reject("SOURCE_OPERATIONS_REQUIRED")

    def test_official_status_and_identity_conflicts_fail_closed(self):
        self.detail["ongoingYn"] = "N"
        self.refresh_hashes()
        self.reject("SOURCE_NOT_CURRENT")
        self.detail["ongoingYn"] = "Y"
        self.detail["instNm"] = "다른기관"
        self.refresh_hashes()
        self.reject("SOURCE_IDENTITY_CONFLICT")

    def test_exact_prompt_version_and_slot_format(self):
        changes = [
            ({"prompt_sha256": "b" * 64}, "ENTRY_PROMPT_MISMATCH"),
            ({"format_id": "reader_story"}, "ENTRY_FORMAT_MISMATCH"),
            ({"scheduled_at": "2026-11-06T16:00:00+09:00"}, "ENTRY_SLOT_MISMATCH"),
            ({"scheduled_at": "2026-11-06T12:00:00"}, "SLOT_TIMEZONE"),
            ({"scheduled_at": "2026-11-06T12:01:00+09:00"}, "SLOT_NOT_SCHEDULED"),
        ]
        for change, reason in changes:
            with self.subTest(change=change):
                entry = deepcopy(self.entry)
                entry.update(change)
                self.reject(reason, entry=entry)

    def test_cta_is_exact_once_last_and_separated(self):
        original = self.entry["writer"]["post_text"]
        bodies = [original.replace(CTA, "프로필링크 확인"), original + "\n#커리어픽", CTA + "\n\n" + original,
                  original.replace("\n\n" + CTA, "\n" + CTA)]
        for body in bodies:
            with self.subTest(body=body):
                self.entry["writer"]["post_text"] = body
                self.reject("BODY_CTA_CONTRACT")

    def test_urls_hashtags_and_competing_calls_to_action_are_blocked(self):
        original = self.entry["writer"]["post_text"]
        for insert, reason in [
            ("https://example.com", "BODY_LINK_OR_HASHTAG"),
            ("example.kr/지원", "BODY_LINK_OR_HASHTAG"),
            ("#채용", "BODY_LINK_OR_HASHTAG"),
            ("궁금한 점은 댓글로 남겨주세요.", "BODY_OTHER_ACTION"),
            ("필요한 친구에게 공유하세요.", "BODY_OTHER_ACTION"),
        ]:
            with self.subTest(insert=insert):
                self.entry["writer"]["post_text"] = insert + "\n\n" + original
                self.reject(reason)

    def test_over_limit_draft_and_extra_replies_never_reach_publisher(self):
        original = deepcopy(self.entry["writer"])
        self.entry["writer"]["post_text"] = "가" * 451 + "\n\n" + CTA
        self.reject("BODY_LENGTH_OR_WHITESPACE")
        self.entry["writer"] = deepcopy(original)
        self.entry["writer"]["status"] = "draft"
        self.reject("WRITER_NOT_READY")
        self.entry["writer"] = deepcopy(original)
        self.entry["writer"]["reply_texts"] = ["보충 답글"]
        self.reject("WRITER_OUTPUT_CONTRACT")

    def test_unresolved_or_unverified_review_cannot_be_promoted_to_ready(self):
        original = deepcopy(self.entry["writer"]["review"])
        for change, reason in [
            ({"missing_or_conflicting": ["필수 자격 첨부 미확인"]}, "REVIEW_UNRESOLVED"),
            ({"verification_basis": "supplied_material_only"}, "REVIEW_BASIS_UNVERIFIED"),
            ({"media_check": "needs_confirmation"}, "REVIEW_MEDIA_OR_LENGTH"),
            ({"length_check": "estimated_with_margin"}, "REVIEW_MEDIA_OR_LENGTH"),
            ({"checked_at": "2026-11-06T13:00:00+09:00"}, "REVIEW_SOURCE_STALE"),
            ({"reference_at": "2026-11-06T13:00:00+09:00"}, "REVIEW_REFERENCE_TIME"),
        ]:
            self.entry["writer"]["review"] = {**deepcopy(original), **change}
            with self.subTest(change=change):
                self.reject(reason)

    def test_application_evidence_is_retained_and_cited(self):
        period = self.entry["writer"]["review"]["application_period"]
        period["source_ref"] = "https://unread.example/source"
        self.reject("APPLICATION_EVIDENCE_REQUIRED")
        period["source_ref"] = "alio-detail.json#a700"
        period["evidence"] = "새로운 접수기간을 실제 읽지 않고 추측한 문장"
        self.reject("APPLICATION_EVIDENCE_REQUIRED")

    def test_date_only_start_does_not_invent_midnight(self):
        self.validate()
        period = self.entry["writer"]["review"]["application_period"]
        period["start"] = "2026-11-06"
        self.reject("APPLICATION_START_TIME_UNKNOWN")
        period["current_open_verified"] = True
        period["current_open_evidence"] = "2026년 11월 6일 10시 현재 온라인 원서 접수 중"
        self.entry["writer"]["review"]["source_refs"][0]["excerpt"] = period["current_open_evidence"]
        period["evidence"] = self.period_evidence.replace("11. 1.", "11. 6.")
        self.detail["scrnprcdrMthdExpln"] = period["evidence"]
        self.refresh_hashes()
        self.validate()

    def test_end_date_only_today_and_elapsed_exact_time_are_rejected(self):
        period = self.entry["writer"]["review"]["application_period"]
        period.update(end="2026-11-06", date_only=True)
        self.reject("APPLICATION_END_TIME_UNKNOWN")
        period.update(end=self.now.isoformat(), date_only=False)
        self.reject("APPLICATION_CLOSED")
        period.update(end="2026-11-06T11:59:00+09:00", date_only=False)
        self.reject("APPLICATION_CLOSED")

    def test_profile_destination_needs_verified_same_notice_mapping(self):
        target = self.entry["writer"]["review"]["profile_target"]
        original = deepcopy(target)
        for changes, reason in [
            ({"verified": False}, "PROFILE_TARGET_UNVERIFIED"),
            ({"notice_id": "a701"}, "PROFILE_TARGET_UNVERIFIED"),
            ({"notice_url": "https://kllollain-max.github.io/supportpick/"}, "PROFILE_TARGET_UNTRUSTED"),
            ({"notice_url": "https://kllollain-max.github.io.evil.test/careerpick/jobs/700.html"}, "PROFILE_TARGET_UNTRUSTED"),
            ({"notice_url": "https://kllollain-max.github.io/careerpick/%2e%2e/supportpick/"}, "PROFILE_TARGET_UNTRUSTED"),
        ]:
            self.entry["writer"]["review"]["profile_target"] = {**original, **changes}
            with self.subTest(changes=changes):
                self.reject(reason)

    def test_scoped_job_count_and_title_require_official_evidence(self):
        image = self.entry["image_job"]
        image["count"] = 1
        self.reject("IMAGE_COUNT_UNSUPPORTED")
        review = self.entry["writer"]["review"]
        excerpt = "보안관제 분야 정보보안 담당자 1명, 정규직, 서울 근무"
        review["source_refs"].append({"url": "https://official.example/jobs/700", "excerpt": excerpt, "checked_at": review["checked_at"]})
        review["fact_evidence"] = [{"field": "count", "value": 1, "source_ref": "https://official.example/jobs/700", "excerpt": excerpt}]
        self.validate()
        image["title"] = "보안관제 분야 정보보안 담당자"
        self.reject("IMAGE_TITLE_UNSUPPORTED")
        review["fact_evidence"].append({"field": "title", "value": image["title"], "source_ref": "https://official.example/jobs/700", "excerpt": excerpt})
        self.validate()
        review["fact_evidence"][0]["excerpt"] = "2명 모집이라는 다른 원문"
        self.reject("IMAGE_COUNT_UNSUPPORTED")

    def test_mixed_employment_cannot_be_claimed_for_every_unit(self):
        self.detail["hireTypeNmLst"] = "정규직,무기계약직"
        self.refresh_hashes()
        self.reject("IMAGE_EMPLOYMENT_UNIT_UNVERIFIED")
        review = self.entry["writer"]["review"]
        excerpt = "정보보안 담당자는 정규직으로 채용합니다."
        review["source_refs"][0]["excerpt"] = excerpt
        review["fact_evidence"] = [{"field": "employment", "value": "정규직", "source_ref": "alio-detail.json#a700", "excerpt": excerpt}]
        self.validate()

    def test_unknown_count_is_not_converted_into_a_number(self):
        self.detail["recrutNope"] = "00명"
        self.refresh_hashes()
        self.entry["image_job"]["count"] = 0
        self.reject("IMAGE_COUNT_INVALID")
        self.entry["image_job"]["count"] = None
        self.validate()

    def test_past_failed_notice_and_same_day_format_are_not_reused(self):
        self.history["records"] = [{"job_id": "a700", "status": "failed"}]
        self.reject("NOTICE_ALREADY_USED")
        self.history["records"] = [{"job_id": "a699", "status": "published", "scheduled_at": "2026-11-06T08:00:00+09:00", "format_id": "key_facts", "text": "다른 도입"}]
        self.reject("DAILY_FORMAT_ALREADY_USED")

    def test_consecutive_exact_hook_is_not_saved_as_a_new_format(self):
        self.history["records"] = [{"status": "published", "text": self.entry["writer"]["post_text"].splitlines()[0] + "\n\n이전 공고"}]
        self.entry["writer"]["review"]["repetition_check"] = "checked"
        self.reject("CONSECUTIVE_HOOK_DUPLICATE")

    def test_publisher_cannot_use_future_or_expired_queue_slot(self):
        queue = {"schema_version": 1, "entries": [self.entry]}
        for now in (self.now, self.slot + timedelta(hours=2)):
            with self.subTest(now=now), self.assertRaisesRegex(QueueValidationError, "PUBLISH_SLOT_NOT_CURRENT"):
                select_ready(queue, self.slot, now, self.history, self.source, self.details, self.policy)
        result = select_ready(queue, self.slot, self.slot + timedelta(minutes=30), self.history, self.source, self.details, self.policy)
        self.assertEqual(result["job_id"], "a700")

    def test_duplicate_queue_slot_or_notice_blocks_consumption(self):
        for offset, reason in [(0, "QUEUE_DUPLICATE_SLOT"), (4, "QUEUE_DUPLICATE_NOTICE")]:
            other = deepcopy(self.entry)
            other["scheduled_at"] = (self.slot + timedelta(hours=offset)).isoformat()
            queue = {"schema_version": 1, "entries": [self.entry, other]}
            with self.subTest(offset=offset), self.assertRaisesRegex(QueueValidationError, reason):
                select_ready(queue, self.slot, self.slot, self.history, self.source, self.details, self.policy)

    def test_empty_queue_does_not_fall_back_to_legacy_copy(self):
        with self.assertRaisesRegex(QueueValidationError, "QUEUE_SLOT_MISSING"):
            select_ready({"schema_version": 1, "entries": []}, self.slot, self.slot, self.history, self.source, self.details, self.policy)

    def test_application_dates_and_time_must_match_the_retained_excerpt(self):
        period = self.entry["writer"]["review"]["application_period"]
        period["end"] = "2026-11-19T17:00:00+09:00"
        self.reject("APPLICATION_END_EVIDENCE_MISMATCH")
        period["end"] = "2026-11-18T18:00:00+09:00"
        self.reject("APPLICATION_END_TIME_EVIDENCE_MISMATCH")
        period.update(end="2026-11-18", date_only=True)
        self.reject("APPLICATION_END_PRECISION_CONFLICT")

    def test_month_day_slashes_and_korean_clock_are_supported(self):
        period = self.entry["writer"]["review"]["application_period"]
        for excerpt in (
            "원서접수는 11/1부터 11/18 17:00까지입니다.",
            "접수기간 11. 1.(일) ~ 11. 18.(수) 오후 5시까지",
        ):
            with self.subTest(excerpt=excerpt):
                period["evidence"] = excerpt
                self.detail["scrnprcdrMthdExpln"] = excerpt
                self.refresh_hashes()
                self.validate()

    def test_image_clock_must_match_verified_application_end(self):
        self.entry["image_job"]["deadline_label"] = "2026-11-18 23:59"
        self.reject("IMAGE_DEADLINE_LABEL_CONFLICT")

    def test_format_metadata_cannot_disguise_a_narrative_as_key_facts(self):
        self.entry["writer"]["post_text"] = "예시연구원 정보보안 모집이에요.\n\n정규직으로 근무해요.\n\n정보보안 기사 자격이 필요해요.\n\n" + CTA
        self.reject("FORMAT_FACT_LABELS_REQUIRED")

    def test_malformed_history_fails_with_a_safe_reason(self):
        self.history["records"] = [{"status": "failed", "job_ids": None}]
        self.reject("HISTORY_SCHEMA")


if __name__ == "__main__":
    unittest.main()
