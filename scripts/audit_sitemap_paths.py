#!/usr/bin/env python3
"""Read-only sitemap URL path audit. Does not deploy or rewrite files."""
from pathlib import Path
from urllib.parse import urlsplit
import sys
import xml.etree.ElementTree as ET

EXPECTED_HOST = "kllollain-max.github.io"
EXPECTED_PREFIX = "/careerpick/"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

def audit(path: Path):
    root = ET.parse(path).getroot()
    urls = [(node.text or "").strip() for node in root.findall(".//sm:loc", NS)]
    if not urls:
        raise ValueError("No sitemap URLs found")
    bad = []
    for url in urls:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != EXPECTED_HOST or not parsed.path.startswith(EXPECTED_PREFIX):
            bad.append(url)
    return urls, bad

if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sitemap.xml")
    try:
        urls, bad = audit(source)
    except (OSError, ET.ParseError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"Checked {len(urls)} URLs; invalid base paths: {len(bad)}")
    for url in bad[:30]:
        print(f"INVALID {url}")
    if len(bad) > 30:
        print(f"... and {len(bad) - 30} more")
    sys.exit(1 if bad else 0)
