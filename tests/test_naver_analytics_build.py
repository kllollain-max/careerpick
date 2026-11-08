import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_public_site import (
    BASE,
    NAVER_ANALYTICS_SCRIPT,
    NAVER_ANALYTICS_STYLE,
    install_naver_analytics,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]


class NaverAnalyticsBuildTests(unittest.TestCase):
    def fixture(self, root):
        for relative in ("index.html", "jobs/a1.html", "guides/index.html"):
            page = root / relative
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text("<!doctype html><html><head><title>공고</title></head>"
                            "<body><main>보존할 공고와 안내</main></body></html>", encoding="utf-8")
        for name in ("naver-analytics.js", "naver-analytics.css"):
            shutil.copyfile(ROOT / name, root / name)
        (root / "sitemap.xml").write_text(
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'
            + BASE + '</loc></url></urlset>', encoding="utf-8")
        (root / "work24-policy.json").write_text('{"approved": false}')
        (root / "push-config.js").write_text('window.CP_ONESIGNAL_APP_ID = "";\n'
                                            'window.CP_PUSH_BROADCAST_ENABLED = false;\n')

    def test_public_pages_include_consent_assets_once_and_preserve_body(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            original = {p: p.read_text(encoding="utf-8") for p in root.rglob("*.html")}
            install_naver_analytics(root)
            self.assertEqual(validate(root)["html_files"], 3)
            for page, before in original.items():
                after = page.read_text(encoding="utf-8")
                self.assertEqual(after.count(NAVER_ANALYTICS_SCRIPT), 1)
                self.assertEqual(after.count(NAVER_ANALYTICS_STYLE), 1)
                self.assertEqual(after.replace(NAVER_ANALYTICS_STYLE + "\n", "")
                                 .replace(NAVER_ANALYTICS_SCRIPT + "\n", ""), before)
            first = {p: p.read_bytes() for p in original}
            install_naver_analytics(root)
            self.assertEqual(first, {p: p.read_bytes() for p in original})

    def test_missing_or_duplicate_loader_fails_public_validation(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), TemporaryDirectory() as temp:
                root = Path(temp)
                self.fixture(root)
                install_naver_analytics(root)
                page = root / "index.html"
                content = page.read_text(encoding="utf-8")
                content = content.replace(NAVER_ANALYTICS_SCRIPT,
                                          NAVER_ANALYTICS_SCRIPT * 2 if duplicate else "")
                page.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Missing or duplicate consent-gated analytics"):
                    validate(root)

    def test_unguarded_naver_and_advertising_scripts_remain_blocked(self):
        for snippet in ('<script src="https://wcs.pstatic.net/wcslog.js"></script>',
                        '<script>wcs_add["wa"]="unexpected";wcs_do();</script>',
                        '<script src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"></script>'):
            with self.subTest(snippet=snippet), TemporaryDirectory() as temp:
                root = Path(temp)
                self.fixture(root)
                install_naver_analytics(root)
                page = root / "index.html"
                page.write_text(page.read_text(encoding="utf-8").replace("</body>", snippet + "</body>"), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Disabled external script"):
                    validate(root)

    def test_incomplete_document_fails_instead_of_silently_losing_coverage(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "broken.html").write_text("<html><head></head><body>incomplete")
            with self.assertRaisesRegex(ValueError, "complete HTML document"):
                install_naver_analytics(root)

    def test_missing_published_asset_is_detected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            install_naver_analytics(root)
            (root / "naver-analytics.js").unlink()
            with self.assertRaisesRegex(ValueError, "naver-analytics.js"):
                validate(root)
        manifest = json.loads((ROOT / "public-files.json").read_text(encoding="utf-8"))
        self.assertIn("naver-analytics.js", manifest["root_files"])
        self.assertIn("naver-analytics.css", manifest["root_files"])


if __name__ == "__main__":
    unittest.main()
