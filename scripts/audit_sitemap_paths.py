#!/usr/bin/env python3
"""Read-only audit of final CareerPick public build sitemap; never mutates source."""
import sys
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

HOST = "kllollain-max.github.io"
PREFIX = "/careerpick/"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

def audit(sitemap: Path):
    urls = [(n.text or "").strip() for n in ET.parse(sitemap).findall(".//s:loc", NS)]
    if not urls:
        raise ValueError("No sitemap URLs")
    bad = []
    for url in urls:
        p = urlsplit(url)
        if p.scheme != "https" or p.netloc != HOST or not p.path.startswith(PREFIX) or p.query or p.fragment:
            bad.append(url)
    return urls, bad

if __name__ == "__main__":
    # Audit generated dist, not the legacy source sitemap; the public build normalizes URLs.
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/sitemap.xml")
    if source.resolve() == Path("sitemap.xml").resolve():
        print("ERROR: audit generated dist/sitemap.xml, not source sitemap.xml", file=sys.stderr)
        sys.exit(2)
    try:
        urls, bad = audit(source)
    except (OSError, ET.ParseError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"Generated sitemap URLs: {len(urls)}; invalid URLs: {len(bad)}")
    for url in bad[:20]:
        print("INVALID", url)
    sys.exit(1 if bad else 0)
