#!/usr/bin/env python3
"""Build an offline restoration from approved public snapshots only.

No collector, credential, external API, publisher or notification sender runs.
The original public snapshots are never rewritten; only dist/ is regenerated.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlparse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HOST = "kllollain-max.github.io"
PREFIX = "/careerpick/"
BASE = "https://" + HOST + PREFIX
OLD_HOST = "jobinfo-hub.github.io"
SOURCE_JSON = ("gojobs.json", "alio.json", "alio-detail.json", "monitor.json", "posts.json", "qnet.json", "enterprise_jobs.json")
BLOCKED_SCRIPT_MARKERS = ("googlesyndication.com", "wcs.pstatic.net", "wcs_add", "wcs_do(", "adsbygoogle")
SCRIPT = re.compile(r"<script\b[^>]*>[\s\S]*?</script\s*>", re.I)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_files() -> list[Path]:
    manifest = json.loads((ROOT / "public-files.json").read_text(encoding="utf-8"))
    names = list(manifest["root_files"]) + list(manifest["files"]) + ["gojobs.json"]
    for directory, extensions in manifest["directories"].items():
        names.extend(str(p.relative_to(ROOT)) for p in (ROOT / directory).iterdir()
                     if p.is_file() and p.suffix in extensions)
    if (ROOT / "exam-status.json").is_file():
        names.append("exam-status.json")
    result = []
    for name in sorted(set(names)):
        posix = PurePosixPath(name)
        if posix.is_absolute() or any(part in {"..", "."} or part.startswith(".") for part in posix.parts):
            raise ValueError("Unsafe public source path: " + name)
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Missing or unsafe public source: " + name)
        result.append(path)
    return result


class LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in (("href",) if tag in {"a", "link"} else ("src",) if tag in {"script", "img", "source"} else ()):
            value = attrs.get(key)
            if value:
                self.links.append(value)


def check_local_url(value: str, page: Path, output: Path) -> str | None:
    if value.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
        return None
    base = BASE + page.relative_to(output).as_posix()
    parsed = urlparse(urljoin(base, value))
    if parsed.netloc != HOST:
        return None
    if not parsed.path.startswith(PREFIX):
        return str(page.relative_to(output)) + " -> outside project: " + value
    relative = unquote(parsed.path[len(PREFIX):])
    candidate = output / relative
    if candidate.is_dir() or parsed.path.endswith("/"):
        candidate = candidate / "index.html"
    if not candidate.resolve().is_relative_to(output) or not candidate.is_file():
        return page.relative_to(output).as_posix() + " -> " + value
    return None


def validate(output: Path) -> dict:
    failures = []
    html_count = 0
    checked_links = 0
    for page in output.rglob("*.html"):
        html_count += 1
        content = page.read_text(encoding="utf-8")
        if OLD_HOST in content:
            failures.append("Old host in " + str(page.relative_to(output)))
        for script in SCRIPT.findall(content):
            if any(marker in script for marker in BLOCKED_SCRIPT_MARKERS):
                failures.append("Disabled external script in " + str(page.relative_to(output)))
        parser = LocalLinks()
        parser.feed(content)
        for link in parser.links:
            checked_links += 1
            missing = check_local_url(link, page, output)
            if missing:
                failures.append(missing)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [x.text for x in ET.parse(output / "sitemap.xml").findall("s:url/s:loc", ns)]
    if len(urls) != len(set(urls)):
        failures.append("Duplicate sitemap URL")
    for url in urls:
        if urlparse(url).netloc != HOST or not url.startswith(BASE):
            failures.append("Noncanonical sitemap URL")
        missing = check_local_url(url, output / "index.html", output)
        if missing:
            failures.append(missing)
    if json.loads((output / "work24-policy.json").read_text()) != {"approved": False}:
        failures.append("Work24 approval gate changed")
    push_config = (output / "push-config.js").read_text()
    if not re.search(r'window\.CP_ONESIGNAL_APP_ID\s*=\s*"(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?";', push_config):
        failures.append("Invalid public push app identifier")
    if 'window.CP_PUSH_BROADCAST_ENABLED = false;' not in push_config:
        failures.append("Push broadcast must remain disabled")
    forbidden = {"docs", "tests", "scripts", ".github", "instagram", "instagram-media", "threads-images", "local-git-objects-partial"}
    for path in output.rglob("*"):
        relative = path.relative_to(output)
        if any(part in forbidden for part in relative.parts) or path.suffix in {".py", ".zip", ".sqlite", ".pack"}:
            failures.append("Nonpublic path " + relative.as_posix())
    if failures:
        raise ValueError("Public output checks failed:\n" + "\n".join(sorted(set(failures))[:50]))
    return {"html_files": html_count, "html_links_checked": checked_links, "sitemap_urls": len(urls), "missing_local_links": 0}


def main() -> dict:
    output = ROOT / "dist"
    if output.is_symlink():
        raise ValueError("dist must not be a symlink")
    inputs = {name: digest(ROOT / name) for name in SOURCE_JSON}
    files = public_files()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()
    for source in files:
        target = output / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    # Use the preserved official ALIO rows for the static first view.
    alio = json.loads((output / "alio.json").read_text())
    blogs = json.loads((output / "posts.json").read_text())
    static_posts = alio["posts"] + [p for p in blogs["posts"] if p.get("type") != "j"]
    sitegen = load_module("careerpick_sitegen", "sitegen.py")
    sitegen.ROOT = output
    sitegen.generate(static_posts)

    pages = load_module("careerpick_job_pages", "scripts/build_job_pages.py")
    pages.ROOT = output
    pages.DATA, pages.DETAIL, pages.OUT = output / "alio.json", output / "alio-detail.json", output / "jobs"
    pages.main()
    report = output / "job-quality-report.json"
    if report.exists():
        report.replace(ROOT / "build-job-quality-report.json")
    prune = load_module("careerpick_prune", "scripts/prune_expired_job_schema.py")
    removed = prune.run(output / "jobs")
    sitemap = load_module("careerpick_sitemap", "scripts/build_sitemap.py")
    sitemap.ROOT, sitemap.SITEMAP, sitemap.JOBS = output, output / "sitemap.xml", output / "jobs"
    sitemap.main()
    (output / ".nojekyll").write_text("")

    # Scope canonical URLs, root links, PWA and inline JS to the project.
    for file in output.rglob("*"):
        if file.suffix not in {".html", ".js", ".css", ".xml", ".txt", ".webmanifest"}:
            continue
        text = file.read_text(encoding="utf-8")
        text = re.sub(r"https://kllollain-max\.github\.io/(?!careerpick/)", BASE, text)
        text = re.sub(r"((?:href|src|action)=[\"'])/(?!/|careerpick/)", lambda m: m[1] + PREFIX, text)
        text = re.sub(r"([\"'`])/(?=(?:jobs|guides|data|onesignal)/)", lambda m: m[1] + PREFIX, text)
        if file.name == "manifest.webmanifest":
            manifest = json.loads(text)
            manifest["start_url"], manifest["scope"] = PREFIX + "?src=app", PREFIX
            text = json.dumps(manifest, ensure_ascii=False, indent=2)
        file.write_text(text, encoding="utf-8")
    checks = validate(output)
    for name, original in inputs.items():
        if digest(ROOT / name) != original or digest(output / name) != original:
            raise ValueError("Source snapshot changed: " + name)
    result = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "site_url": BASE,
        "source_snapshot": "repository",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "alio_snapshot_at": alio["updated"],
        "alio_rows": len(alio["posts"]),
        "output_files": sum(p.is_file() for p in output.rglob("*")),
        "expired_archived_schema_removed": removed,
        "source_sha256": inputs,
        "source_json_unchanged": True,
        "network_collection_performed": False,
        "deployed": False,
        **checks,
    }
    (ROOT / "build-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
