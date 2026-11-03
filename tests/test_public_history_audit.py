import hashlib
import json
import subprocess
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from scripts.audit_public_history import KEY_NAMES, audit


class PublicHistoryAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.keys = {name: hashlib.sha256(("fixture-" + name).encode()).hexdigest() + "/+==" for name in KEY_NAMES}
        self.git("init", "-q")
        self.git("config", "user.name", "Audit Fixture")
        self.git("config", "user.email", "audit@example.invalid")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def commit(self, name, content):
        (self.repo / name).write_text(content)
        self.git("add", "--", name)
        self.git("commit", "-qm", "fixture")

    def test_clean_history_keeps_hashes_and_secret_references(self):
        self.commit("config.txt", "ALIO_KEY: ${{ secrets.ALIO_KEY }}\n" + hashlib.sha256(b"public-data").hexdigest())
        result = audit(self.repo, self.keys)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["history_scan_complete"])
        self.assertEqual(result["commits_scanned"], 1)
        self.assertEqual(result["blobs_scanned"], 1)
        self.assertEqual(result["findings"], [])

    def test_removed_encoded_registered_credential_is_found_without_value(self):
        secret = self.keys["ALIO_KEY"]
        escaped = urllib.parse.quote(secret, safe="")
        self.commit("legacy.txt", escaped)
        self.commit("legacy.txt", "clean current file")
        result = audit(self.repo, self.keys)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["commits_scanned"], 2)
        self.assertEqual(result["blobs_scanned"], 2)
        self.assertEqual(result["findings"][0]["category"], "registered_secret_ALIO_KEY")
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(escaped, json.dumps(result))

    def test_obvious_token_and_private_key_patterns_are_reported_without_values(self):
        token = "gh" + "p_" + "X7" * 20
        private_key = "-----BEGIN " + "PRIVATE KEY-----\n" + "QUJD" * 32 + "\n-----END " + "PRIVATE KEY-----"
        self.commit("bad.txt", token + "\n" + private_key)
        result = audit(self.repo, self.keys)
        self.assertEqual({finding["category"] for finding in result["findings"]}, {"github_token", "private_key"})
        self.assertNotIn(token, json.dumps(result))
        self.assertNotIn(private_key, json.dumps(result))

    def test_missing_key_blocks_even_when_git_is_clean(self):
        self.commit("clean.txt", "public text")
        keys = dict(self.keys)
        keys.pop("GOJOBS_KEY")
        result = audit(self.repo, keys)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["history_scan_complete"])
        self.assertFalse(result["registered_credential_coverage_complete"])
        self.assertEqual(result["reason"], "registered_credentials_missing_or_short")

    def test_quoted_json_credential_field_is_detected_without_value(self):
        value = hashlib.sha256(b"unregistered-json-fixture").hexdigest()
        self.commit("config.json", json.dumps({"api_key": value}))
        result = audit(self.repo, self.keys)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["findings"][0]["category"], "hardcoded_api_credential")
        self.assertEqual(result["findings"][0]["path"], "config.json")
        self.assertNotIn(value, json.dumps(result))

    def test_credential_in_filename_is_redacted(self):
        escaped = urllib.parse.quote(self.keys["DATA_GO_KR_KEY"], safe="")
        self.commit(escaped + ".txt", self.keys["DATA_GO_KR_KEY"])
        result = audit(self.repo, self.keys)
        self.assertEqual(result["findings"][0]["path"], "[redacted-path]")
        self.assertNotIn(escaped, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
