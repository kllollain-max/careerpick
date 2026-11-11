"""No live network: CAS conflicts, uncertain writes and ledger preservation."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import os
import unittest
from unittest.mock import Mock, patch
import urllib.error

from scripts import threads_performance as perf
from scripts import threads_performance_store as store
from tests import test_threads_performance as performance_fixtures


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class PerformanceStoreTests(unittest.TestCase):
    def setUp(self):
        fixture = performance_fixtures.PerformanceTests()
        fixture.setUp()
        self.history, self.now = fixture.history, fixture.now
        self.empty = {"schema_version": 1, "policy_id": perf.POLICY_ID, "observations": [],
                      "checkpoints": {"7d": {"reported": False}}, "unrelated": {"preserve": True}}
        self.obs = perf.observation(fixture.item(), captured_at=self.now, metrics={"views": 12})
        self.other = perf.observation(fixture.item(), captured_at=self.now + timedelta(minutes=1),
                                      metrics={"views": 14})
        self.backend = store.GitHubPerformanceState("test-token-never-real", opener=Mock())

    def test_get_reads_only_fixed_repo_branch_and_path(self):
        opener = Mock(return_value=response({"sha": "a" * 40, "encoding": "base64",
            "content": base64.b64encode(json.dumps(self.empty).encode()).decode()}))
        backend = store.GitHubPerformanceState("test-token-never-real", opener=opener)
        sha, state = backend.read()
        self.assertEqual(sha, "a" * 40)
        self.assertEqual(state, self.empty)
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url,
            "https://api.github.com/repos/kllollain-max/careerpick/contents/threads/performance.json?ref=threads-publisher-state")

    def test_404_only_initializes_after_existing_branch_verified(self):
        error = urllib.error.HTTPError("redacted", 404, "missing", {}, None)
        opener = Mock(side_effect=[error, response({"ref": "refs/heads/threads-publisher-state",
                                                   "object": {"sha": "b" * 40}})])
        sha, state = store.GitHubPerformanceState("test-token-never-real", opener=opener).read()
        self.assertIsNone(sha)
        self.assertEqual(state["observations"], [])
        self.assertEqual(opener.call_args_list[1].args[0].get_method(), "GET")
        self.assertTrue(opener.call_args_list[1].args[0].full_url.endswith("/git/ref/heads/threads-publisher-state"))

    def test_missing_or_wrong_branch_is_not_initialized(self):
        error = urllib.error.HTTPError("redacted", 404, "missing", {}, None)
        opener = Mock(side_effect=[error, response({"ref": "refs/heads/main", "object": {"sha": "b" * 40}})])
        with self.assertRaisesRegex(store.StateError, "branch unverified"):
            store.GitHubPerformanceState("test-token-never-real", opener=opener).read()

    def test_other_repository_context_cannot_write(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "kllollain-max/supportpick"}):
            with self.assertRaisesRegex(store.StateError, "Unexpected repository"):
                store.GitHubPerformanceState("test-token-never-real")

    def test_put_is_single_fixed_path_cas_and_preserves_fields(self):
        self.backend._opener.return_value = response({"content": {"sha": "c" * 40}})
        state = perf.merge_observations(self.empty, [self.obs])
        self.backend.put("a" * 40, state)
        request = self.backend._opener.call_args.args[0]
        payload = json.loads(request.data)
        decoded = json.loads(base64.b64decode(payload["content"]))
        self.assertEqual(request.get_method(), "PUT")
        self.assertTrue(request.full_url.endswith("/contents/threads/performance.json"))
        self.assertEqual(payload["branch"], "threads-publisher-state")
        self.assertEqual(payload["sha"], "a" * 40)
        self.assertEqual(decoded["checkpoints"], self.empty["checkpoints"])
        self.assertEqual(decoded["unrelated"], self.empty["unrelated"])

    def test_conflict_rereads_and_merges_concurrent_observation_and_checkpoint(self):
        concurrent = perf.merge_observations(self.empty, [self.other])
        concurrent["checkpoints"]["7d"]["reported"] = True
        final = perf.merge_observations(concurrent, [self.obs])
        with patch.object(self.backend, "read", side_effect=[("a" * 40, self.empty),
                ("b" * 40, concurrent), ("c" * 40, final)]), \
             patch.object(self.backend, "put", side_effect=[store.RequestError(409), "c" * 40]) as put:
            saved, result = self.backend.append([self.obs])
        self.assertEqual(result["status"], "saved_verified")
        self.assertEqual(put.call_args_list[1].args[0], "b" * 40)
        second_state = put.call_args_list[1].args[1]
        self.assertTrue(second_state["checkpoints"]["7d"]["reported"])
        self.assertEqual(len(second_state["observations"]), 2)
        self.assertEqual(saved, final)

    def test_uncertain_write_success_requires_exact_readback_not_second_put(self):
        final = perf.merge_observations(self.empty, [self.obs])
        with patch.object(self.backend, "read", side_effect=[("a" * 40, self.empty), ("b" * 40, final)]), \
             patch.object(self.backend, "put", side_effect=store.RequestError(uncertain=True)) as put:
            saved, result = self.backend.append([self.obs])
        put.assert_called_once()
        self.assertEqual(result["status"], "verified_after_uncertain_write")
        self.assertEqual(saved, final)

    def test_uncertain_missing_write_stops_without_blind_retry(self):
        with patch.object(self.backend, "read", return_value=("a" * 40, self.empty)), \
             patch.object(self.backend, "put", side_effect=store.RequestError(uncertain=True)) as put:
            with self.assertRaisesRegex(store.StateError, "persistence unconfirmed"):
                self.backend.append([self.obs])
        put.assert_called_once()

    def test_duplicate_observation_is_noop_but_changed_identity_blocks(self):
        final = perf.merge_observations(self.empty, [self.obs])
        with patch.object(self.backend, "read", return_value=("a" * 40, final)), \
             patch.object(self.backend, "put") as put:
            _, result = self.backend.append([self.obs])
            self.assertEqual(result["status"], "already_saved")
            changed = deepcopy(self.obs)
            changed["metrics"]["views"] = 999
            with self.assertRaisesRegex(store.StateError, "Immutable observation conflict"):
                self.backend.append([changed])
        put.assert_not_called()

    def test_conflicts_are_bounded(self):
        with patch.object(self.backend, "read", return_value=("a" * 40, self.empty)), \
             patch.object(self.backend, "put", side_effect=store.RequestError(409)) as put:
            with self.assertRaisesRegex(store.StateError, "remained conflicted"):
                self.backend.append([self.obs])
        self.assertEqual(put.call_count, 3)

    def test_no_due_observations_make_no_write(self):
        backend = Mock()
        backend.read.return_value = ("a" * 40, self.empty)
        collector = Mock(return_value=(deepcopy(self.empty), {"status": "no_due_observations"}))
        result = store.run(self.history, backend=backend, now=self.now, collector=collector)
        backend.append.assert_not_called()
        self.assertEqual(result["persistence"]["status"], "no_new_observations")
        self.assertFalse(collector.call_args.kwargs["include_history"])

    def test_persistence_failure_keeps_concrete_observations_in_artifact(self):
        backend = Mock()
        backend.read.return_value = ("a" * 40, self.empty)
        backend.append.side_effect = store.StateError("Measurement persistence unconfirmed")
        collected = perf.merge_observations(self.empty, [self.obs])
        collector = Mock(return_value=(collected, {"status": "measured"}))
        result = store.run(self.history, backend=backend, now=self.now, collector=collector)
        self.assertEqual(result["persistence"]["status"], "unconfirmed")
        self.assertEqual(result["state"]["observations"], [self.obs])

    def test_collector_cannot_modify_existing_measurement(self):
        initial = perf.merge_observations(self.empty, [self.obs])
        changed = deepcopy(initial)
        changed["observations"][0]["metrics"]["views"] = 90
        backend = Mock()
        backend.read.return_value = ("a" * 40, initial)
        with self.assertRaisesRegex(store.StateError, "attempted to change"):
            store.run(self.history, backend=backend, now=self.now,
                      collector=Mock(return_value=(changed, {"status": "measured"})))
        backend.append.assert_not_called()

    def test_github_error_never_surfaces_token_or_response_body(self):
        body = io.BytesIO(b'{"message":"test-token-never-real"}')
        opener = Mock(side_effect=urllib.error.HTTPError("test-token-never-real", 403,
                                                       "test-token-never-real", {}, body))
        backend = store.GitHubPerformanceState("test-token-never-real", opener=opener)
        with self.assertRaises(store.RequestError) as error:
            backend.read()
        self.assertNotIn("test-token", str(error.exception))

    def test_72h_observation_is_valid_and_can_be_conditionally_saved(self):
        fixture = performance_fixtures.V5PerformanceTests()
        fixture.setUp()
        observation = fixture.make_observation(hours=72)
        final = perf.merge_observations(self.empty, [observation])
        store.validate_state(final)
        with patch.object(self.backend, "read", side_effect=[("a" * 40, self.empty), ("b" * 40, final)]), \
             patch.object(self.backend, "put", return_value="b" * 40) as put:
            saved, result = self.backend.append([observation])
        self.assertEqual(result["status"], "saved_verified")
        self.assertEqual(saved["observations"][0]["window"], "72h")
        put.assert_called_once()

    def test_account_snapshot_only_is_saved_without_inventing_post_metrics(self):
        account = perf.account_observation(captured_at=self.now, followers_count=120,
                                           source="existing_authorized_insights")
        final = perf.merge_account_observations(self.empty, [account])
        with patch.object(self.backend, "read", side_effect=[("a" * 40, self.empty), ("b" * 40, final)]), \
             patch.object(self.backend, "put", return_value="b" * 40):
            saved, result = self.backend.append([], account_additions=[account])
        self.assertEqual(saved["observations"], [])
        self.assertEqual(saved["account_observations"], [account])
        self.assertEqual(result["status"], "saved_verified")

    def test_uncertain_account_snapshot_write_is_verified_without_retransmission(self):
        account = perf.account_observation(captured_at=self.now, followers_count=0,
                                           source="existing_authorized_insights")
        final = perf.merge_account_observations(self.empty, [account])
        with patch.object(self.backend, "read", side_effect=[("a" * 40, self.empty), ("b" * 40, final)]), \
             patch.object(self.backend, "put", side_effect=store.RequestError(uncertain=True)) as put:
            saved, result = self.backend.append([], account_additions=[account])
        put.assert_called_once()
        self.assertEqual(result["status"], "verified_after_uncertain_write")
        self.assertEqual(saved, final)

    def test_run_preserves_existing_accounts_and_saves_actual_new_snapshot(self):
        old_account = perf.account_observation(captured_at=self.now, followers_count=120,
                                               source="existing_authorized_insights")
        new_account = perf.account_observation(captured_at=self.now + timedelta(days=1), followers_count=123,
                                               source="existing_authorized_insights")
        initial = perf.merge_account_observations(self.empty, [old_account])
        final = perf.merge_account_observations(initial, [new_account])
        backend = Mock()
        backend.read.return_value = ("a" * 40, initial)
        backend.append.return_value = (final, {"status": "saved_verified"})
        result = store.run(self.history, backend=backend, now=self.now + timedelta(days=1),
            collector=Mock(return_value=(deepcopy(initial), {"status": "no_due_observations"})),
            account_observations=[new_account])
        backend.append.assert_called_once_with([], account_additions=[new_account])
        self.assertEqual(result["state"]["account_observations"], [old_account, new_account])

    def test_account_observation_identity_collision_and_wrong_scope_are_blocked(self):
        account = perf.account_observation(captured_at=self.now, followers_count=120,
                                           source="existing_authorized_insights")
        initial = perf.merge_account_observations(self.empty, [account])
        changed = deepcopy(account)
        changed["followers_count"] = 999
        with patch.object(self.backend, "read", return_value=("a" * 40, initial)), \
             patch.object(self.backend, "put") as put:
            with self.assertRaisesRegex(store.StateError, "account observation conflict"):
                self.backend.append([], account_additions=[changed])
        put.assert_not_called()
        changed["account"] = "hid_1004"
        with self.assertRaisesRegex(store.StateError, "Account observation invalid"):
            store.validate_state({"schema_version": 1, "observations": [], "account_observations": [changed]})

    def test_live_report_uses_post_collection_clock_for_just_captured_metrics(self):
        captured = self.now + timedelta(milliseconds=500)
        account = perf.account_observation(captured_at=captured, followers_count=12, source="actual_insight")
        final = perf.merge_account_observations(self.empty, [account])
        backend = Mock()
        backend.read.return_value = ("a" * 40, self.empty)
        backend.append.return_value = (final, {"status": "saved_verified"})
        with patch.object(store, "datetime") as clock:
            clock.now.side_effect = [self.now, self.now + timedelta(seconds=1)]
            result = store.run(self.history, backend=backend,
                collector=Mock(return_value=(final, {"status": "measured"})))
        report = result["summary"]["v5_performance"]["account_followers"]
        self.assertEqual(report["status"], "baseline_only")
        self.assertEqual(report["observed_start"], captured.isoformat())


if __name__ == "__main__":
    unittest.main()
