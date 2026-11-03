"""Offline sitemap generation regression for existing URLs and job changes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import xml.etree.ElementTree as ET

import build_sitemap as generator

def main():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs = root / "jobs"
        jobs.mkdir()
        (root / "guides").mkdir()
        (root / "guides" / "index.html").write_text("<html></html>", encoding="utf-8")
        (root / "guides" / "qualification-preference-guide.html").write_text("<html></html>", encoding="utf-8")
        (jobs / "a100.html").write_text("<html></html>", encoding="utf-8")
        (jobs / "a200.html").write_text("<html></html>", encoding="utf-8")
        site = root / "sitemap.xml"
        site.write_text("""<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://kllollain-max.github.io/</loc></url>
<url><loc>https://kllollain-max.github.io/jobs/a999.html</loc></url>
<url><loc>https://kllollain-max.github.io/jobs/a100.html</loc></url>
<url><loc>https://kllollain-max.github.io/guides/removed.html</loc></url>
</urlset>""", encoding="utf-8")
        with patch.object(generator, "ROOT", root), patch.object(generator, "SITEMAP", site), patch.object(generator, "JOBS", jobs):
            generator.main()
            ns = {"s": generator.NS}
            def urls():
                tree = ET.parse(site)
                return [el.text for el in tree.findall("s:url/s:loc", ns)]
            found = urls()
            assert "https://kllollain-max.github.io/" in found
            assert "https://kllollain-max.github.io/jobs/a999.html" not in found
            assert "https://kllollain-max.github.io/jobs/a100.html" in found
            assert "https://kllollain-max.github.io/jobs/a200.html" in found
            assert "https://kllollain-max.github.io/guides/" in found
            assert "https://kllollain-max.github.io/guides/qualification-preference-guide.html" in found
            assert "https://kllollain-max.github.io/guides/removed.html" not in found
            assert len(found) == len(set(found))
            generator.main()
            assert urls() == found
            (root / "guides" / "index.html").unlink()
            (jobs / "a100.html").unlink()
            generator.main()
            assert "https://kllollain-max.github.io/jobs/a100.html" not in urls()
            assert "https://kllollain-max.github.io/guides/" not in urls()
    print("Sitemap generator regression PASS: preserve, add, prune, idempotence")

if __name__ == "__main__":
    main()
