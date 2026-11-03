import base64
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import private_alert_backlog_store as store


class PrivateBacklogStoreTests(unittest.TestCase):
    def test_missing_backlog_requires_initialization(self):
        error = HTTPError("https://api.github.com/x", 404, "not found", {}, None)
        with patch.object(store, "_config", return_value=("private-owner/private-repo", "token")):
            with patch.object(store, "_request", side_effect=error):
                self.assertEqual(store.read_backlog(), (None, None))

    def test_valid_empty_private_backlog_read(self):
        raw = base64.b64encode(json.dumps({"version": 1, "jobs": []}).encode()).decode()
        with patch.object(store, "_config", return_value=("private-owner/private-repo", "token")):
            with patch.object(store, "_request", return_value={"sha": "abc", "content": raw}):
                self.assertEqual(store.read_backlog(), ([], "abc"))

    def test_missing_sha_never_writes(self):
        with patch.object(store, "_request", side_effect=AssertionError("must not write")):
            with self.assertRaises(RuntimeError):
                store.save_backlog([], None)

    def test_conflict_does_not_overwrite(self):
        error = HTTPError("https://api.github.com/x", 409, "conflict", {}, None)
        with patch.object(store, "_config", return_value=("private-owner/private-repo", "token")):
            with patch.object(store, "_request", side_effect=error):
                with self.assertRaisesRegex(RuntimeError, "concurrently"):
                    store.save_backlog([], "sha")

    def test_invalid_payload_is_rejected(self):
        raw = base64.b64encode(b'{"version":1,"jobs":"invalid"}').decode()
        with patch.object(store, "_config", return_value=("private-owner/private-repo", "token")):
            with patch.object(store, "_request", return_value={"sha": "abc", "content": raw}):
                with self.assertRaises(ValueError):
                    store.read_backlog()


if __name__ == "__main__":
    unittest.main()
