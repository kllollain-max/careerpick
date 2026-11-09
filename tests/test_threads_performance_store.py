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


if __name__ == "__main__":
    unittest.main()
