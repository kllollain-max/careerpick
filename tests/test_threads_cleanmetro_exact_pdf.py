"""Exact employer-origin PDF only: no wildcard, no source digest bypass."""
import subprocess
import unittest
from unittest import mock
from scripts.threads_reviewed_ingest import (
    CLEANMETRO_2026_17_PDF, official_url_allowed, fetch_official_digest,
)


class ExactOriginalPdfTest(unittest.TestCase):
    def test_only_pinned_original_url(self):
        self.assertTrue(official_url_allowed(CLEANMETRO_2026_17_PDF))
        bad = [
            CLEANMETRO_2026_17_PDF.replace("wr_id=430", "wr_id=429"),
            CLEANMETRO_2026_17_PDF.replace("no=11", "no=12"),
            CLEANMETRO_2026_17_PDF + "&nonce=guessed",
            CLEANMETRO_2026_17_PDF.replace("cleanmetro.co.kr", "evil.co.kr"),
            CLEANMETRO_2026_17_PDF.replace("https:", "http:"),
            "https://cleanmetro.co.kr/bbs/download.php?bo_table=recruit&wr_id=430&no=15",
        ]
        for url in bad:
            with self.subTest(url=url):
                self.assertFalse(official_url_allowed(url))

    @mock.patch("scripts.threads_reviewed_ingest.subprocess.run")
    def test_exact_pdf_digest_verified_without_shell(self, run):
        expected = "a" * 64
        run.return_value.stdout = expected + "\n"
        self.assertEqual(fetch_official_digest(CLEANMETRO_2026_17_PDF), expected)
        run.assert_called_once()
        args = run.call_args
        self.assertEqual(args.args[0][0], "node")
        self.assertIn("threads_cleanmetro_original_pdf_digest.cjs", args.args[0][1])
        self.assertEqual(args.kwargs.get("check"), True)
        self.assertEqual(args.kwargs.get("timeout"), 130)

    @mock.patch("scripts.threads_reviewed_ingest.subprocess.run")
    def test_bad_or_missing_pdf_fail_closed(self, run):
        for bad in ("", "not-a-pdf", "bad" * 21):
            run.return_value.stdout = bad
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "OFFICIAL_DOCUMENT_DIGEST_INVALID"):
                    fetch_official_digest(CLEANMETRO_2026_17_PDF)
        run.side_effect = subprocess.TimeoutExpired("node", 130)
        with self.assertRaisesRegex(ValueError, "OFFICIAL_SOURCE_UNAVAILABLE"):
            fetch_official_digest(CLEANMETRO_2026_17_PDF)


if __name__ == "__main__":
    unittest.main()
