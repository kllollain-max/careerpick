"""Bounded read-only host/site audit. Does not execute JS, request ads or prove indexing."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

HOST = 'https://kllollain-max.github.io/'
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
LIMIT = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Observe redirects; never follow to another host or into an ad URL.


def fetch(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.netloc != urlsplit(HOST).netloc or p.query or p.fragment:
        raise ValueError('outside_host')
    try:
        with build_opener(NoRedirect()).open(Request(url, headers={'User-Agent': 'Pick-Public-Readiness/1.0'}), timeout=15) as response:
            raw = response.read(LIMIT + 1)
            if len(raw) > LIMIT:
                return {'status': 'unverified', 'error': 'body_limit'}, b''
            return {'status': response.status, 'sha256': hashlib.sha256(raw).hexdigest(),
                    'headers': response.headers.get_all('X-Robots-Tag', [])}, raw
    except HTTPError as error:
        return {'status': error.code}, b''
    except (OSError, ValueError) as error:
        return {'status': 'unverified', 'error': type(error).__name__}, b''


class Head(HTMLParser):
    def __init__(self, raw):
        super().__init__(); self.canonicals = []; self.robots = []; self.publishers = []; self.h1 = 0
        self.feed(raw.decode('utf-8-sig'))
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'h1': self.h1 += 1
        if tag == 'link' and a.get('rel') == 'canonical': self.canonicals.append(a.get('href'))
        if tag == 'meta' and a.get('name', '').lower() in {'robots', 'googlebot'}: self.robots.append(a.get('content', ''))
        if tag == 'meta' and a.get('name') == 'google-adsense-account': self.publishers.append(a.get('content', ''))


def blocked(values):
    return any({'noindex', 'none'} & set(re.split(r'[\s,]+', value.lower())) for value in values)


def run(project, loader=fetch):
    if project not in {'careerpick', 'supportpick'}: raise ValueError('unknown_project')
    base = HOST + project + '/'
    report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'project': project,
              'registrationSite': HOST.rstrip('/'), 'independentPathRegistration': False,
              'errors': [], 'unverified': [], 'observations': {},
              'indexing': 'not_observed', 'adsenseApproval': 'not_observed'}
    def read(url):
        item, raw = loader(url)
        report['observations'][url] = item
        if item['status'] != 200:
            report['unverified' if item['status'] == 'unverified' else 'errors'].append(url + ': ' + str(item['status']))
        return item, raw
    _, root = read(HOST)
    _, ads = read(HOST + 'ads.txt')
    _, robots = read(HOST + 'robots.txt')
    _, xml = read(base + 'sitemap.xml')
    try:
        publishers = Head(root).publishers
        if len(publishers) != 1 or not re.fullmatch(r'ca-pub-\d{16}', publishers[0]):
            report['errors'].append('missing_or_ambiguous_host_publisher_meta')
        else:
            publisher = publishers[0].removeprefix('ca-')
            rows = [line.split('#', 1)[0].strip().split(',') for line in ads.decode().splitlines()]
            if not any([v.strip() for v in row] == ['google.com', publisher, 'DIRECT', 'f08c47fec0942fa0'] for row in rows):
                report['errors'].append('host_ads_txt_publisher_mismatch')
        tree = ET.fromstring(xml)
        if tree.tag != '{' + NS['s'] + '}urlset': raise ValueError('sitemap_namespace')
        urls = [node.text or '' for node in tree.findall('s:url/s:loc', NS)]
        if not urls or len(urls) != len(set(urls)): raise ValueError('sitemap_empty_or_duplicate')
        for url in urls:
            p = urlsplit(url)
            if not url.startswith(base) or p.query or p.fragment or '..' in p.path.split('/'):
                raise ValueError('sitemap_scope')
        report['sitemapUrls'] = len(urls)
        required = [base + p for p in ('', 'about.html', 'privacy.html', 'contact.html')]
        if project == 'supportpick': required.append(base + 'terms.html')
        for url in required:
            if url not in urls: report['errors'].append('required_url_missing: ' + url)
        # Two independent content types, deterministic sample; no 11k-page daily crawl.
        prefixes = ('jobs/', 'guides/') if project == 'careerpick' else ('benefits/',)
        selected = required[:]
        for prefix in prefixes:
            matches = sorted(u for u in urls if u.startswith(base + prefix) and u != base + prefix)
            if not matches: report['errors'].append('missing_content_type: ' + prefix)
            selected += matches[:2]
        if project == 'supportpick':
            for sid in ('149200000026', '105100000001'):
                url = base + 'benefits/' + sid + '/'
                if url in urls and url not in selected: selected.append(url)
        parser = RobotFileParser(); parser.parse(robots.decode().splitlines())
        for url in selected:
            for agent in ('Googlebot', 'Mediapartners-Google', 'Google-Display-Ads-Bot'):
                if not parser.can_fetch(agent, url): report['errors'].append('robots_disallow: ' + agent + ' ' + url)
            item, raw = read(url)
            if item['status'] != 200: continue
            doc = Head(raw)
            if doc.canonicals != [url]: report['errors'].append('canonical_mismatch: ' + url)
            if blocked(doc.robots + item.get('headers', [])): report['errors'].append('noindex: ' + url)
            if not doc.h1: report['errors'].append('missing_h1: ' + url)
        if project == 'supportpick':
            _, raw = read(base + 'site-manifest.json')
            manifest = json.loads(raw)
            report['publicRevision'] = manifest.get('sourceRevision')
            report['publicGeneration'] = manifest.get('generation')
            report['benefits'] = manifest.get('benefits')
            expected = manifest.get('files', {})
            for url, observation in report['observations'].items():
                if not url.startswith(base): continue
                name = url[len(base):]
                if name == '' or name.endswith('/'): name += 'index.html'
                if name in expected and observation.get('sha256') != expected[name]:
                    report['errors'].append('public_manifest_hash_mismatch: ' + name)
            # A deployment during this audit must not be mistaken for a coherent pass.
            second, raw2 = loader(base + 'site-manifest.json')
            if second['status'] != 200 or raw2 != raw: report['unverified'].append('public_release_changed_during_audit')
    except (ValueError, UnicodeError, ET.ParseError, TypeError, AttributeError) as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--project', required=True, choices=['careerpick', 'supportpick'])
    p.add_argument('--output', default='public-readiness-report.json'); args = p.parse_args()
    result = run(args.project)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result['errors'] else 2 if result['unverified'] else 0)
