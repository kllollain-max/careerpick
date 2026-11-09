"""Offline measurement boundaries: no POSTs, fabricated views or draft A/B."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import unittest
from unittest.mock import Mock, patch
import urllib.error

from scripts import threads_performance as perf


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.published = datetime(2026, 11, 10, 3, 30, tzinfo=timezone.utc)
        self.now = self.published + timedelta(hours=24, minutes=20)
        self.state = {"schema_version": 1, "observations": []}
        self.record = {
            "job_id": "a123", "threads_post_id": "123", "status": "published",
            "request_status": "confirmed", "published_at": self.published.isoformat(),
            "scheduled_at": "2026-11-10T12:00:00+09:00", "format_id": "key_facts",
            "text": "공공기관 보안직 정규직을 뽑아요.\n본문", "image_url": "",
            "reply_status": "confirmed", "reply_post_id": "456",
            "writer_review": {"reach_editorial": {"policy_id": perf.POLICY_ID,
                "hook_type": "A", "first_sentence": "공공기관 보안직 정규직을 뽑아요.",
                "experiment_eligible": True,
                "comparison_context": {"comparison_group": "verified-security-seoul",
                    "comparison_group_evidence": "공식 모집표의 정규직 보안직·서울·1명·필수 정보보안기사", "audience_scope": "정보보안기사 보유자"}},
                "application_period": {"end": "2026-11-24T17:00:00+09:00", "date_only": False}},
            "writer_entry": {"image_job": {"org": "공공기관", "title": "보안직",
                "count": 1, "employment": "정규직", "location": "서울"}},
        }
        self.history = {"records": [self.record], "posted_ids": ["a123"]}
        self.public_reader = Mock(return_value={"id": "123", "text": self.record["text"], "is_reply": False})

    def verified_item(self, item, record=None):
        record = record or self.record
        proof = perf.public_main_evidence(record, {"id": record["threads_post_id"],
            "text": record["text"], "is_reply": False}, self.now)
        item = deepcopy(item)
        item["metadata"] = perf.publication_metadata(record, proof)
        return item

    def item(self, now=None, window="24h", history=None):
        plan = perf.measurement_plan(history or self.history, self.state, now or self.now)
        return self.verified_item(next(i for i in plan["items"] if i["window"] == window))

    def test_plan_uses_actual_main_time_and_keeps_seven_day_pending(self):
        plan = perf.measurement_plan(self.history, self.state, self.now)
        self.assertEqual(plan["main_posts"], 1)
        self.assertEqual([x["status"] for x in plan["items"]], ["due", "pending"])
        self.assertEqual(plan["items"][0]["post_id"], "123")
        self.assertEqual(plan["items"][0]["due_at"], (self.published + timedelta(days=1)).isoformat())
        self.assertNotIn("456", [x["post_id"] for x in plan["items"]])

    def test_unknown_count_is_not_zero_and_text_keeps_reviewed_facts(self):
        self.record["writer_entry"]["image_job"]["count"] = "00명"
        metadata = perf.publication_metadata(self.record)
        self.assertIsNone(metadata["recruitment_unit_count"])
        self.assertEqual(metadata["employment"], "정규직")
        self.assertEqual(metadata["media"], "TEXT")

    def test_comparison_context_preserves_new_and_existing_audience_fields(self):
        context = self.record["writer_review"]["reach_editorial"]["comparison_context"]
        del context["audience_scope"]
        context.update(audience_breadth="간호사 면허 소지자", notice_type="공개경쟁", eligibility_basis="공식 자격요건")
        metadata = perf.publication_metadata(self.record)
        self.assertEqual(metadata["audience_scope"], "간호사 면허 소지자")
        self.assertEqual(metadata["audience_breadth"], "간호사 면허 소지자")
        self.assertEqual(metadata["notice_type"], "공개경쟁")
        self.assertEqual(metadata["comparison_context"], context)
        context["audience_scope"] = "원래 기록한 대상 범위"
        self.assertEqual(perf.publication_metadata(self.record)["audience_scope"], "원래 기록한 대상 범위")

    def test_zero_missing_and_reader_replies_are_distinct(self):
        result = perf.observation(self.item(), captured_at=self.now, metrics={"views": 0, "likes": 0, "replies": 1})
        self.assertEqual(result["metrics"]["views"], 0)
        self.assertEqual(result["metric_status"]["views"], "observed")
        self.assertIsNone(result["metrics"]["quotes"])
        self.assertEqual(result["metric_status"]["quotes"], "not_provided")
        self.assertEqual(result["metrics"]["replies"], 1)
        self.assertIsNone(result["reader_replies"])
        self.assertEqual(result["automated_detail_reply_id"], "456")
        self.assertIsNone(result["applications"])

    def test_late_historical_cumulative_is_never_comparable_24h(self):
        late = self.published + timedelta(days=12)
        item = self.item(now=late)
        result = perf.observation(item, captured_at=late, metrics={"views": 1000})
        self.assertEqual(result["timing"], "late_cumulative")
        self.assertFalse(result["comparable_milestone"])
        self.assertEqual(result["elapsed_seconds"], 12 * 86400)
        state = perf.merge_observations(self.state, [result])
        summary = perf.summarize(self.history, state, late)
        self.assertIsNone(summary["groups"]["24h"]["A"]["views_median"])

    def test_first_line_mismatch_and_unconfirmed_main_exclude_ab(self):
        self.record["text"] = "🏢 공공기관\n정형 문구"
        self.assertEqual(perf.hook_status(self.record)["reason"], "final_first_sentence_mismatch")
        self.record["text"] = "공공기관 보안직 정규직을 뽑아요.\n본문"
        self.record["request_status"] = "sending"
        self.assertEqual(perf.hook_status(self.record)["reason"], "main_receipt_unconfirmed")

    def test_old_posts_are_measured_only_explicitly_and_never_ab(self):
        del self.record["writer_review"]["reach_editorial"]
        self.assertEqual(perf.measurement_plan(self.history, self.state, self.now)["main_posts"], 0)
        plan = perf.measurement_plan(self.history, self.state, self.now, include_history=True)
        self.assertEqual(plan["main_posts"], 1)
        self.assertFalse(plan["items"][0]["metadata"]["hook"]["eligible"])

    def test_collect_calls_only_main_once_for_multiple_past_windows(self):
        late = self.published + timedelta(days=8)
        guard, collect = Mock(), Mock(return_value={"metrics": {"views": 51}})
        state, result = perf.collect_due(self.history, self.state, late, token="test-not-real",
            account_guard=guard, collector=collect, public_reader=self.public_reader, clock=lambda: late)
        guard.assert_called_once()
        collect.assert_called_once_with("123", "test-not-real")
        self.public_reader.assert_called_once_with("123", "test-not-real")
        self.assertEqual(result["api_calls"], 2)
        self.assertEqual(result["insight_api_calls"], 1)
        self.assertEqual(len(state["observations"]), 2)
        self.assertTrue(all(not o["comparable_milestone"] for o in state["observations"]))

    def test_permission_denied_is_not_zero_or_retried_next_tick(self):
        collector = Mock(side_effect=urllib.error.HTTPError("redacted", 403, "denied", {}, io.BytesIO()))
        state, result = perf.collect_due(self.history, self.state, self.now, token="test-not-real",
            account_guard=Mock(), collector=collector, public_reader=self.public_reader, clock=lambda: self.now)
        self.assertEqual(result["status"], "unmeasured")
        self.assertEqual(state["observations"][0]["status"], "permission_denied")
        self.assertIsNone(state["observations"][0]["metrics"]["views"])
        _, result2 = perf.collect_due(self.history, state, self.now + timedelta(minutes=1),
            token="test-not-real", account_guard=Mock(), collector=collector, public_reader=self.public_reader)
        self.assertEqual(result2["api_calls"], 0)
        self.assertEqual(collector.call_count, 1)

    def test_failed_measurement_does_not_raise_or_erase_success(self):
        collector = Mock(side_effect=RuntimeError("Never expose this string"))
        state, result = perf.collect_due(self.history, self.state, self.now, token="test-not-real",
            account_guard=Mock(), collector=collector, public_reader=self.public_reader, clock=lambda: self.now)
        self.assertEqual(result["statuses"], {"collection_failed": 1})
        self.assertNotIn("Never expose", str(state))
        plan = perf.measurement_plan(self.history, state, self.now + timedelta(minutes=5))
        self.assertEqual(plan["items"][0]["status"], "retry_deferred")

    def test_absent_token_and_wrong_account_do_not_query_insights(self):
        collector = Mock()
        with patch.dict("os.environ", {}, clear=True):
            state, _ = perf.collect_due(self.history, self.state, self.now, collector=collector,
                                       clock=lambda: self.now)
        self.assertEqual(state["observations"][0]["status"], "access_unavailable")
        state, _ = perf.collect_due(self.history, self.state, self.now, token="test-not-real",
            account_guard=Mock(side_effect=RuntimeError("wrong account")),
            collector=collector, clock=lambda: self.now)
        self.assertEqual(state["observations"][0]["status"], "account_unverified")
        collector.assert_not_called()

    def test_append_only_merge_detects_overwrite_and_is_idempotent(self):
        obs = perf.observation(self.item(), captured_at=self.now, metrics={"views": 12})
        state = perf.merge_observations(self.state, [obs, obs])
        self.assertEqual(len(state["observations"]), 1)
        changed = deepcopy(obs)
        changed["metrics"]["views"] = 99
        with self.assertRaisesRegex(ValueError, "collision"):
            perf.merge_observations(state, [changed])
        self.assertEqual(self.state["observations"], [])

    def test_summary_uses_median_and_does_not_call_eight_significance(self):
        records, observations = [], []
        for arm in ("A", "B"):
            for i in range(8):
                record = deepcopy(self.record)
                record["threads_post_id"] = str(1000 + i + (100 if arm == "B" else 0))
                record["writer_review"]["reach_editorial"]["hook_type"] = arm
                first = f"{arm}{i} 검증한 기관 직무 도입이에요."
                record["text"] = first + "\n본문"
                record["writer_review"]["reach_editorial"]["first_sentence"] = first
                records.append(record)
                item = perf.measurement_plan({"records": [record]}, self.state, self.now)["items"][0]
                observations.append(perf.observation(self.verified_item(item, record), captured_at=self.now,
                    metrics={"views": 10000 if i == 7 else 10 + i, "likes": 0}))
        state = perf.merge_observations(self.state, observations)
        report = perf.summarize({"records": records}, state, self.now)
        self.assertEqual(report["groups"]["24h"]["A"]["views_median"], 13.5)
        self.assertTrue(report["initial_8_per_arm_target_met"])
        self.assertFalse(report["statistical_significance_claim"])
        self.assertEqual(report["normal_main_publications"], 16)
        self.assertEqual(report["confirmed_detail_replies"], 16)

    def test_identical_public_first_sentence_across_arms_is_invalid(self):
        other = deepcopy(self.record)
        other["threads_post_id"] = "124"
        other["writer_review"]["reach_editorial"]["hook_type"] = "B"
        history = {"records": [self.record, other]}
        items = [i for i in perf.measurement_plan(history, self.state, self.now)["items"] if i["window"] == "24h"]
        records_by_id = {"123": self.record, "124": other}
        observations = [perf.observation(self.verified_item(i, records_by_id[i["post_id"]]),
                        captured_at=self.now, metrics={"views": 10}) for i in items]
        report = perf.summarize(history, perf.merge_observations(self.state, observations), self.now)
        self.assertEqual(report["groups"]["24h"]["A"]["count"], 0)
        self.assertEqual(report["excluded_observations"]["identical_final_hook_across_arms"], 2)

    def test_checkpoints_start_at_actual_new_policy_post_and_wait_for_7d(self):
        state = perf.merge_observations(self.state, [perf.observation(self.item(), captured_at=self.now, metrics={"views": 10})])
        report = perf.summarize(self.history, state, self.now)
        self.assertEqual(report["experiment_start"], self.published.isoformat())
        self.assertEqual(report["seven_day_pending_posts"], 1)
        self.assertEqual(report["checkpoints"][0]["status"], "pending")
        report = perf.summarize(self.history, state, self.published + timedelta(days=14))
        self.assertEqual([c["status"] for c in report["checkpoints"]], ["due", "due"])

    def test_reporting_window_does_not_restart_original_experiment(self):
        state = perf.merge_observations(self.state, [perf.observation(self.item(), captured_at=self.now, metrics={"views": 10})])
        report = perf.summarize(self.history, state, self.published + timedelta(days=35))
        self.assertEqual(report["normal_main_publications"], 0)
        self.assertEqual(report["experiment_start"], self.published.isoformat())
        self.assertEqual(report["checkpoints"][1]["status"], "due")

    def test_confirmed_ledger_without_public_get_cannot_enter_ab(self):
        item = perf.measurement_plan(self.history, self.state, self.now)["items"][0]
        observation = perf.observation(item, captured_at=self.now, metrics={"views": 5000})
        state = perf.merge_observations(self.state, [observation])
        # A previously written timestamp is not a substitute for public text evidence.
        state["experiment_start"] = self.published.isoformat()
        report = perf.summarize(self.history, state, self.now)
        self.assertEqual(report["groups"]["24h"]["A"]["count"], 0)
        self.assertIsNone(report["experiment_start"])
        self.assertEqual(report["excluded_observations"]["public_main_unverified"], 1)

    def test_actual_public_mismatch_keeps_metrics_but_excludes_ab(self):
        before = deepcopy((self.history, self.state))
        reader = Mock(return_value={"id": "123", "text": "다르게 공개된 첫 문장\n본문", "is_reply": False})
        collector = Mock(return_value={"metrics": {"views": 5000}})
        state, result = perf.collect_due(self.history, self.state, self.now, token="test-not-real",
            account_guard=Mock(), collector=collector, public_reader=reader, clock=lambda: self.now)
        record = state["observations"][0]
        self.assertEqual(result["status"], "measured")
        self.assertEqual(record["metrics"]["views"], 5000)
        self.assertEqual(record["public_verification"]["status"], "mismatch")
        self.assertEqual(record["public_verification"]["actual_first_sentence"], "다르게 공개된 첫 문장")
        report = perf.summarize(self.history, state, self.now)
        self.assertEqual(report["groups"]["24h"]["A"]["count"], 0)
        self.assertEqual(report["excluded_observations"]["public_main_text_mismatch"], 1)
        self.assertIsNone(report["experiment_start"])
        self.assertEqual((self.history, self.state), before)

    def test_public_read_failure_keeps_measurement_and_excludes_ab(self):
        reader = Mock(side_effect=RuntimeError("secret-bearing error must not escape"))
        state, result = perf.collect_due(self.history, self.state, self.now, token="test-not-real",
            account_guard=Mock(), collector=Mock(return_value={"metrics": {"views": 0}}),
            public_reader=reader, clock=lambda: self.now)
        self.assertEqual(result["status"], "measured")
        self.assertEqual(state["observations"][0]["metrics"]["views"], 0)
        self.assertNotIn("secret-bearing", str(state))
        report = perf.summarize(self.history, state, self.now)
        self.assertEqual(report["groups"]["24h"]["A"]["count"], 0)
        self.assertEqual(report["excluded_observations"]["public_main_read_failed"], 1)

    def test_remote_id_and_main_type_are_required_even_when_text_matches(self):
        for payload in ({"id": "999", "text": self.record["text"], "is_reply": False},
                        {"id": "123", "text": self.record["text"], "is_reply": True},
                        {"id": "123", "text": self.record["text"]}):
            with self.subTest(payload=payload):
                proof = perf.public_main_evidence(self.record, payload, self.now)
                self.assertFalse(perf.hook_status(self.record, proof)["eligible"])

    def test_public_reader_performs_only_main_get_with_header_credential(self):
        opener = Mock(return_value=io.BytesIO(json.dumps({"id": "123", "text": "공개본문", "is_reply": False}).encode()))
        result = perf.read_public_main("123", "test-not-real", opener=opener)
        self.assertEqual(result["text"], "공개본문")
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.startswith("https://graph.threads.net/v1.0/123?"))
        self.assertNotIn("test-not-real", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-not-real")
        self.assertIsNone(request.data)

    def test_later_public_verification_does_not_retroactively_validate_old_snapshot(self):
        unverified = perf.measurement_plan(self.history, self.state, self.now)["items"][0]
        old = perf.observation(unverified, captured_at=self.now, metrics={"views": 99})
        late = self.now + timedelta(hours=2)
        verified = self.verified_item(self.item(now=late))
        new = perf.observation(verified, captured_at=late, metrics={"views": 101})
        state = perf.merge_observations(self.state, [old, new])
        report = perf.summarize(self.history, state, late)
        self.assertEqual(report["groups"]["24h"]["A"]["count"], 0)
        self.assertEqual(report["excluded_observations"]["public_main_unverified"], 1)


if __name__ == "__main__":
    unittest.main()
