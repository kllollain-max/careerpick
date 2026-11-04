"""Offline search audit for the actual public output, without account writes."""
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://kllollain-max.github.io/careerpick/'
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


def same_url(left, right):
    def parts(value):
        u = urlparse(value)
        return u.scheme, u.netloc, unquote(u.path), u.query, u.fragment
    return parts(left) == parts(right)


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.descriptions = []
        self.description_tag = ''
        self.canonicals = []
        self.robots = []
        self.links = []
        self.h1 = 0
        self.schemas = []
        self._title = False
        self._json = False
        self._json_text = ''
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title':
            self._title = True
        if tag == 'h1':
            self.h1 += 1
        if tag == 'a':
            self.links.append(a.get('href', ''))
        if tag == 'link' and a.get('rel') == 'canonical':
            self.canonicals.append(a.get('href', ''))
        if tag == 'meta' and a.get('name', '').lower() == 'description':
            self.descriptions.append(a.get('content', ''))
            self.description_tag = self.get_starttag_text()
        if tag == 'meta' and a.get('name', '').lower() in {'robots', 'googlebot', 'yeti'}:
            self.robots.append(a.get('content', '').lower())
        if tag == 'script' and a.get('type', '').lower() == 'application/ld+json':
            self._json = True
            self._json_text = ''

    def handle_endtag(self, tag):
        if tag == 'title':
            self._title = False
        if tag == 'script' and self._json:
            try:
                self.schemas.append(json.loads(self._json_text))
            except ValueError:
                self.schemas.append({'parse_error': True})
            self._json = False

    def handle_data(self, data):
        if self._title:
            self.title += data
        if self._json:
            self._json_text += data

    @property
    def noindex(self):
        return any('noindex' in re.split(r'[\s,]+', value) for value in self.robots)


def normalize_duplicate_metadata(output, writer=None):
    """Disambiguate notice metadata with its existing URL identity, not new facts.

    Keep bodies, canonical URLs, structured data, and personal records untouched.
    This does not resolve substantive duplicate content or assert editorial review.
    """
    rows = [(p, p.read_text(encoding='utf-8')) for p in sorted((output / 'jobs').glob('*.html'))]
    parsed = [(p, text, Page(text)) for p, text in rows]
    titles = Counter(d.title for _, _, d in parsed if d.title)
    descriptions = Counter(d.descriptions[0] for _, _, d in parsed if len(d.descriptions) == 1 and d.descriptions[0])
    changed = 0
    for path, source, doc in parsed:
        if not re.fullmatch(r'(?:a[0-9]+|w[0-9a-f]{24})', path.stem):
            continue
        result = source
        if titles[doc.title] > 1:
            title = html.escape(doc.title + ' | 공고 ' + path.stem)
            result = re.sub(r'<title\b[^>]*>.*?</title>', lambda _: '<title>' + title + '</title>', result, count=1, flags=re.S | re.I)
        if len(doc.descriptions) == 1 and descriptions[doc.descriptions[0]] > 1:
            description = html.escape('공고 ' + path.stem + ' · ' + doc.descriptions[0], quote=True)
            result = result.replace(doc.description_tag, '<meta name="description" content="' + description + '">', 1)
        if result != source:
            if writer:
                writer(path, result)
            else:
                path.write_text(result, encoding='utf-8')
            changed += 1
    return changed


def schema_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from schema_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from schema_nodes(child)


def remove_unverified_archived_schema(output, current_ids, writer=None):
    """Keep archived bodies, but do not offer unverified jobs as active vacancies."""
    removed = 0
    pattern = re.compile(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script\s*>', re.S | re.I)
    for path in sorted((output / 'jobs').glob('*.html')):
        if path.stem in current_ids:
            continue
        source = path.read_text(encoding='utf-8')
        def replace(match):
            nonlocal removed
            doc = Page(match.group(0))
            # Only standalone JobPosting scripts occur in the retained template.
            # Preserve other metadata and mixed graphs for explicit review.
            value = doc.schemas[0] if doc.schemas else None
            kind = value.get('@type') if isinstance(value, dict) else None
            if kind == 'JobPosting' or isinstance(kind, list) and 'JobPosting' in kind:
                removed += 1
                return ''
            return match.group(0)
        result = pattern.sub(replace, source)
        if result != source:
            if writer:
                writer(path, result)
            else:
                path.write_text(result, encoding='utf-8')
    return removed


def inspect(output, at=None):
    at = at or datetime.now(timezone.utc)
    errors, warnings, pages = [], [], {}
    for path in sorted(output.rglob('*.html')):
        relative = path.relative_to(output).as_posix()
        doc = Page(path.read_text(encoding='utf-8'))
        pages[relative] = doc
        expected = BASE + (relative[:-10] if relative.endswith('index.html') else relative)
        if len(doc.canonicals) != 1 or not same_url(doc.canonicals[0], expected):
            errors.append(relative + ': canonical mismatch')
        if not doc.title.strip():
            errors.append(relative + ': missing title')
    locations = [n.text for n in ET.parse(output / 'sitemap.xml').findall('s:url/s:loc', NS)]
    if len(set(locations)) != len(locations):
        errors.append('sitemap: duplicate URL')
    for loc in locations:
        parsed = urlparse(loc)
        if not loc.startswith(BASE) or parsed.scheme != 'https' or parsed.netloc != urlparse(BASE).netloc or parsed.query or parsed.fragment:
            errors.append('sitemap: URL outside canonical project')
            continue
        relative = unquote(parsed.path[len(urlparse(BASE).path):])
        if not relative or relative.endswith('/'):
            relative += 'index.html'
        doc = pages.get(relative)
        if not doc:
            errors.append('sitemap: missing file ' + relative)
            continue
        if doc.noindex:
            errors.append(relative + ': noindex URL in sitemap')
        if len(doc.canonicals) != 1 or not same_url(doc.canonicals[0], loc):
            errors.append(relative + ': sitemap/canonical mismatch')
        if len(doc.descriptions) != 1 or not doc.descriptions[0].strip():
            errors.append(relative + ': missing or multiple descriptions')
        if doc.h1 == 0:
            errors.append(relative + ': missing visible h1')
    title_counts = Counter(d.title for d in pages.values())
    desc_counts = Counter(d.descriptions[0] for d in pages.values() if len(d.descriptions) == 1 and d.descriptions[0])
    duplicate_titles = sum(n > 1 for n in title_counts.values())
    duplicate_descriptions = sum(n > 1 for n in desc_counts.values())
    if duplicate_titles:
        warnings.append('duplicate title groups: ' + str(duplicate_titles))
    if duplicate_descriptions:
        warnings.append('duplicate description groups: ' + str(duplicate_descriptions))
    home = pages.get('index.html')
    home_urls = {urljoin(BASE, href) for href in home.links} if home else set()
    internal_jobs = sorted(url for url in home_urls if url.startswith(BASE + 'jobs/') and url.endswith('.html'))
    if not internal_jobs:
        warnings.append('homepage has no static internal notice links; inspect current feed/empty state')
    schemas = 0
    for relative, doc in pages.items():
        for root in doc.schemas:
            if isinstance(root, dict) and root.get('parse_error'):
                errors.append(relative + ': invalid JSON-LD')
            for schema in schema_nodes(root):
                if schema.get('@type') != 'JobPosting':
                    continue
                schemas += 1
                if not relative.startswith('jobs/'):
                    errors.append(relative + ': JobPosting outside a single notice page')
                expires = schema.get('validThrough')
                if expires:
                    try:
                        end = datetime.fromisoformat(expires.replace('Z', '+00:00'))
                        if end.tzinfo is None:
                            warnings.append(relative + ': expiry timezone requires source confirmation')
                            continue
                        if end < at:
                            errors.append(relative + ': expired JobPosting')
                    except ValueError:
                        errors.append(relative + ': malformed JobPosting expiry')
    return {
        'html_count': len(pages), 'sitemap_urls': len(locations),
        'static_homepage_job_links': len(internal_jobs),
        'duplicate_title_groups': duplicate_titles,
        'duplicate_description_groups': duplicate_descriptions,
        'job_posting_schema_count': schemas,
        'noindex_pages': [path for path, doc in pages.items() if doc.noindex],
        'lastmod_elements': len(ET.parse(output / 'sitemap.xml').findall('s:url/s:lastmod', NS)),
        'errors': sorted(set(errors)), 'warnings': sorted(set(warnings)),
        'limits': ['Offline output only; not proof of Google/Naver indexing, rankings, or rich-result eligibility'],
    }


if __name__ == '__main__':
    report = inspect(ROOT / 'dist')
    (ROOT / 'build-search-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['errors']:
        raise SystemExit(1)
