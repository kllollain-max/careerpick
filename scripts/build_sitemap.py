
"""CareerPick sitemap generator - preserve existing URLs."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
SITEMAP = ROOT / "sitemap.xml"
JOBS = ROOT / "jobs"
BASE = "https://kllollain-max.github.io/careerpick"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

KST = timezone(timedelta(hours=9))

def publication_date(instant=None):
    """Korea date for newly published sitemap entries.

    Existing entries preserve their lastmod so hourly rebuilds do not
    falsely claim a new modification.
    """
    instant = instant if instant is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("publication_date requires timezone-aware datetime")
    return instant.astimezone(KST).date().isoformat()


ET.register_namespace("", NS)
TAG = lambda name: f"{{{NS}}}{name}"


def main():
    if not SITEMAP.exists():
        raise SystemExit("기존 sitemap.xml이 없습니다.")

    tree = ET.parse(SITEMAP)
    root = tree.getroot()
    if root.tag != TAG("urlset"):
        raise SystemExit("올바른 사이트맵 형식이 아닙니다.")

    existing = set()
    # Keep the first entry for each URL. Duplicates can make the hourly
    # sitemap verification fail even when generated job pages are valid.
    for entry in list(root.findall(TAG("url"))):
        loc = entry.findtext(TAG("loc"), default="").strip()
        # Normalize legacy project-root addresses before deduplication/pruning.
        if loc.startswith("https://kllollain-max.github.io/") and not loc.startswith(BASE + "/"):
            loc = BASE + "/" + loc.split("github.io/", 1)[1]
            entry.find(TAG("loc")).text = loc
        # This sitemap is exclusively for the canonical HTTPS GitHub Pages host.
        # External, HTTP and malformed locations must not enter Search Console.
        parsed = urlparse(loc)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "kllollain-max.github.io"
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            root.remove(entry)
        elif loc in existing:
            root.remove(entry)
        else:
            existing.add(loc)

    pages = sorted(JOBS.glob("a[0-9]*.html")) + sorted(JOBS.glob("w*.html"))
    if not pages:
        raise SystemExit("생성된 채용공고 페이지가 없습니다.")

    current_jobs = {
        f"{BASE}/jobs/{page.name}"
        for page in pages
        if page.stem[1:].isdigit() or (page.stem.startswith("w") and len(page.stem)==25 and all(c in "0123456789abcdef" for c in page.stem[1:]))
    }

    # 이전에 등록된 채용공고 주소 중 더 이상
    # 생성되지 않는 페이지는 사이트맵에서 제외
    for entry in list(root.findall(TAG("url"))):
        loc = entry.findtext(TAG("loc"), default="").strip()
        parsed = urlparse(loc)
        if (
            parsed.scheme == "https"
            and parsed.netloc == "kllollain-max.github.io"
            and parsed.path.startswith("/careerpick/jobs/")
            and loc not in current_jobs
        ):
            root.remove(entry)
            existing.discard(loc)

    # 자체 제작 가이드는 존재하는 HTML 파일만 사이트맵에 등록합니다.
    guide_files = sorted((ROOT / "guides").glob("*.html"))
    guide_urls = {
        f"{BASE}/guides/" if page.name == "index.html"
        else f"{BASE}/guides/{page.name}"
        for page in guide_files if page.is_file()
    }

    # Prune removed first-party guides; keep unrelated sitemap entries intact.
    for entry in list(root.findall(TAG("url"))):
        loc = entry.findtext(TAG("loc"), default="").strip()
        parsed = urlparse(loc)
        if (
            parsed.scheme == "https"
            and parsed.netloc == "kllollain-max.github.io"
            and parsed.path.startswith("/careerpick/guides/")
            and loc not in guide_urls
        ):
            root.remove(entry)
            existing.discard(loc)

    added = 0
    today = publication_date()

    for loc in sorted(current_jobs):
        if loc in existing:
            continue
        entry = ET.SubElement(root, TAG("url"))
        ET.SubElement(entry, TAG("loc")).text = loc
        ET.SubElement(entry, TAG("lastmod")).text = today
        added += 1

    # Keep the national civil-service exam page discoverable on every rebuild.
    exam_page = ROOT / "civil-service-exams.html"
    exam_url = f"{BASE}/civil-service-exams.html"
    if exam_page.is_file() and exam_url not in existing:
        entry = ET.SubElement(root, TAG("url"))
        ET.SubElement(entry, TAG("loc")).text = exam_url
        ET.SubElement(entry, TAG("lastmod")).text = today
        existing.add(exam_url)
        added += 1

    for loc in sorted(guide_urls):
        if loc in existing:
            continue
        entry = ET.SubElement(root, TAG("url"))
        ET.SubElement(entry, TAG("loc")).text = loc
        ET.SubElement(entry, TAG("lastmod")).text = today
        existing.add(loc)
        added += 1

    ET.indent(tree, space="  ")
    tree.write(SITEMAP, encoding="utf-8", xml_declaration=True)

    print("현재 채용 상세페이지:", len(current_jobs))
    print("새로 추가한 주소:", added)
    print("사이트맵 전체 주소:", len(root.findall(TAG("url"))))


if __name__ == "__main__":
    main()

