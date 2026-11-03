"""Offline tests for archived JobPosting schema pruning."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.prune_expired_job_schema import prune_html, run

NOW = datetime(2026, 10, 25, 0, tzinfo=timezone.utc)


def page(schema):
    return '<html><head><link rel="canonical" href="https://kllollain-max.github.io/jobs/a1.html"><script type="application/ld+json">' + json.dumps(schema) + '</script></head><body>Official source link</body></html>'


class PruneTests(unittest.TestCase):
    def test_expired_jobposting_removed_but_html_preserved(self):
        src = page({"@type": "JobPosting", "validThrough": "2026-10-21T23:59:00+09:00"})
        output, count = prune_html(src, NOW)
        self.assertEqual(count, 1)
        self.assertNotIn("JobPosting", output)
        self.assertIn('rel="canonical"', output)
        self.assertIn("Official source link", output)

    def test_active_jobposting_preserved(self):
        src = page({"@type": "JobPosting", "validThrough": "2026-10-29T23:59:00+09:00"})
        self.assertEqual(prune_html(src, NOW), (src, 0))

    def test_unknown_deadline_preserved(self):
        for value in (None, "not-a-date"):
            src = page({"@type": "JobPosting", "validThrough": value})
            self.assertEqual(prune_html(src, NOW), (src, 0))

    def test_date_only_means_end_of_day_in_korea(self):
        src = page({"@type": "JobPosting", "validThrough": "2026-10-25"})
        self.assertEqual(prune_html(src, NOW), (src, 0))

    def test_other_structured_data_untouched(self):
        src = page({"@type": "BreadcrumbList", "validThrough": "2020-01-01"})
        self.assertEqual(prune_html(src, NOW), (src, 0))

    def test_check_then_cleanup_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "a123.html"
            p.write_text(page({"@type": "JobPosting", "validThrough": "2026-10-21T23:59:00+09:00"}), encoding="utf-8")
            self.assertEqual(run(root, check=True, now=NOW), 1)
            self.assertEqual(run(root, now=NOW), 1)
            self.assertEqual(run(root, check=True, now=NOW), 0)
            self.assertEqual(run(root, now=NOW), 0)


if __name__ == "__main__":
    unittest.main()
