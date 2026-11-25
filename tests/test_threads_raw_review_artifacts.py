import hashlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from scripts import threads_raw_review_artifacts as m


class RawReviewTests(unittest.TestCase):
    def bundle(self):
        return {"status": "review_required", "approved_for_queue": False, "drafts": [],
                "official_source_alternatives": [{"notice_id": m.NOTICE, "status": "unreviewed",
                    "source_post_sha256": m.POST_SHA, "source_detail_sha256": m.DETAIL_SHA}]}

    def now(self):
        return datetime(2026, 11, 25, 12, tzinfo=m.KST)

    def test_matching_candidate_saves_exact_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            def fetch(url):
                data = b"%PDF-test-only" if url.endswith("3088960") else bytes.fromhex("d0cf11e0a1b11ae1") + b"test-only"
                return data, url, "application/octet-stream"
            result = m.capture(self.bundle(), Path(d), fetch, self.now())
            self.assertEqual(len(result["documents"]), 3)
            self.assertFalse(result["approved_for_queue"])
            self.assertFalse(result["meta_posted"])
            for item in result["documents"]:
                self.assertEqual(item["sha256"], hashlib.sha256((Path(d) / item["name"]).read_bytes()).hexdigest())

    def test_wrong_snapshot_never_downloads(self):
        bundle = self.bundle()
        bundle["official_source_alternatives"][0]["source_detail_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(m.capture(bundle, Path(d), lambda u: self.fail("unexpected GET"), self.now())["documents"], [])

    def test_expired_or_approved_bundle_never_downloads(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(m.capture(self.bundle(), Path(d), lambda u: self.fail("unexpected GET"), m.DEADLINE)["documents"], [])
            bundle = self.bundle()
            bundle["approved_for_queue"] = True
            self.assertEqual(m.capture(bundle, Path(d), lambda u: self.fail("unexpected GET"), self.now())["documents"], [])

    def test_html_error_never_saved_as_attachment(self):
        with tempfile.TemporaryDirectory() as d:
            result = m.capture(self.bundle(), Path(d), lambda u: (b"<html>denied</html>", u, "text/html"), self.now())
            self.assertTrue(all(i["status"] == "unverified" for i in result["documents"]))
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_pdf_alternative_is_review_only(self):
        with tempfile.TemporaryDirectory() as d:
            def fetch(url):
                if "korea.kr" in url:
                    return b"%PDF-test-only", url, "application/octet-stream"
                raise OSError("test denial")
            result = m.capture(self.bundle(), Path(d), fetch, self.now())
            self.assertEqual(result["documents"][0]["status"], "raw_bytes_captured_for_review")
            self.assertEqual(len(result["documents"][0]["attempts"]), 1)
            self.assertEqual(result["semantic_review"], "required")
            self.assertFalse(result["approved_for_queue"])
            self.assertFalse(result["meta_posted"])


if __name__ == "__main__":
    unittest.main()
