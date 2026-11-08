"""Offline regression tests for the read-only final-build sitemap audit."""
import tempfile
import unittest
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

from scripts.audit_sitemap_paths import audit

NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

def write_sitemap(path, urls):
    root = Element(f"{{{NS}}}urlset")
    for url in urls:
        entry = SubElement(root, f"{{{NS}}}url")
        SubElement(entry, f"{{{NS}}}loc").text = url
    ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

class SitemapAuditTests(unittest.TestCase):
    def test_valid_project_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sitemap.xml"
            write_sitemap(path, ["https://kllollain-max.github.io/careerpick/",
                                 "https://kllollain-max.github.io/careerpick/jobs/a123.html"])
            urls, invalid = audit(path)
            self.assertEqual(len(urls), 2)
            self.assertEqual(invalid, [])

    def test_reject_root_and_external_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sitemap.xml"
            bad = ["https://kllollain-max.github.io/jobs/a123.html",
                   "http://kllollain-max.github.io/careerpick/",
                   "https://example.com/careerpick/",
                   "https://kllollain-max.github.io/careerpick/?preview=1"]
            write_sitemap(path, bad)
            self.assertEqual(audit(path)[1], bad)

    def test_empty_sitemap_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sitemap.xml"
            write_sitemap(path, [])
            with self.assertRaises(ValueError):
                audit(path)

if __name__ == "__main__":
    unittest.main()
