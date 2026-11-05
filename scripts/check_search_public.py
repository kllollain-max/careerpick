#!/usr/bin/env python3
"""Read-only public search audit. Fetch HTML/XML, never execute scripts or send ads.

Default: representative URLs. --all-urls is an explicit, bounded one-pass audit.
HTTP/network observations do not establish Google/Naver indexing or bot blocking.
"""
import argparse
import hashlib
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

try:
    from .search_readiness import BASE, Page, same_url, schema_nodes
except ImportError:
    from search_readiness import BASE, Page, same_url, schema_nodes

ROBOTS = 'https://kllollain-max.github.io/robots.txt'
AGENTS = ('Googlebot', 'Yeti', 'Mediapartners-Google', 'Google-Display-Ads-Bot')
LIMIT = 2 * 1024 * 1024
SAMPLES = ('', 'about.html', 'privacy.html', 'contact.html', 'guides/',
           'guides/application-checklist.html', 'guides/qualification-preference-guide.html',
           'guides/recruitment-corrections-guide.html', 'guides/self-introduction-star.html',
           'guides/ncs-study-plan.html', 'guides/after-application-checklist.html')
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
TRANSIENT = {408, 429, 500, 502, 503, 504}


def encoded_url(url):
    parts = urlparse(url)
    return urlunparse(parts._replace(path=quote(parts.path, safe="/:@-._~!$&'()*+,;=%")))


def in_scope(url):
    p = urlparse(url)
    return (p.scheme == 'https' and p.netloc == urlparse(BASE).netloc
            and p.path.startswith(urlparse(BASE).path) and not p.query and not p.fragment
            and '..' not in unquote(p.path).split('/'))


class ProjectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if newurl != ROBOTS and not in_scope(newurl):
            raise ValueError('redirect_outside_allowed_scope')
        return super().redirect_request(request, fp, code, message, headers, newurl)


class Body(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.inside = False; self.skip = 0; self.text = []
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        if tag == 'body': self.inside = True
        if tag in ('script', 'style'): self.skip += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.skip = max(0, self.skip - 1)
        if tag == 'body': self.inside = False
    def handle_data(self, text):
        if self.inside and not self.skip: self.text.append(text.strip())


def fetch(url):
    if url != ROBOTS and not in_scope(url):
        return {'url': url, 'status': 'unverified', 'error': 'outside_allowed_scope'}, None
    url = encoded_url(url)
    item = {'url': url}
    try:
        request = Request(url, headers={'User-Agent': 'CareerPick-Search-Readiness/1.0 (read-only)'})
        with build_opener(ProjectRedirect()).open(request, timeout=15) as response:
            data = response.read(LIMIT + 1)
            item.update(status=response.status, final_url=response.url,
                        content_type=response.headers.get('Content-Type', ''),
                        x_robots_tag=response.headers.get('X-Robots-Tag', ''),
                        last_modified=response.headers.get('Last-Modified'),
                        bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            if len(data) > LIMIT:
                item.update(status='unverified', error='response_exceeds_audit_limit')
                return item, None
            return item, data
    except HTTPError as error:
        item.update(status=error.code, final_url=error.url)
    except Exception as error:
        item.update(status='unverified', error=type(error).__name__)
    return item, None


def sitemap_urls(data):
    root = ET.fromstring(data)
    if root.tag != '{' + NS['s'] + '}urlset':
        raise ValueError('invalid_sitemap_namespace_or_type')
    urls = [n.text or '' for n in root.findall('s:url/s:loc', NS)]
    if not urls or len(urls) > 50000:
        raise ValueError('empty_or_excessive_sitemap')
    if len(urls) != len(set(urls)):
        raise ValueError('duplicate_sitemap_url')
    if any(not in_scope(url) for url in urls):
        raise ValueError('sitemap_url_outside_project')
    return urls


def examine(url, loader=fetch):
    item, data = loader(url)
    item['issues'] = []
    links = set()
    if item['status'] != 200 or data is None:
        return item, links
    if not same_url(item.get('final_url', url), url):
        item['issues'].append('redirect_changes_url')
    if 'html' not in item.get('content_type', '').lower():
        item['issues'].append('non_html_content_type')
    try:
        source = data.decode('utf-8-sig', 'strict')
    except UnicodeError:
        item['issues'].append('invalid_utf8'); return item, links
    doc = Page(source)
    item.update(title=doc.title.strip(), description_count=len(doc.descriptions),
                description=doc.descriptions[0] if len(doc.descriptions) == 1 else '',
                canonical=doc.canonicals, h1=doc.h1,
                visible_text_characters=len(' '.join(Body(source).text)),
                robots=doc.robots)
    if not item['title']: item['issues'].append('missing_title')
    if len(doc.descriptions) != 1 or not doc.descriptions[0].strip():
        item['issues'].append('missing_or_multiple_descriptions')
    if len(doc.canonicals) != 1 or not same_url(doc.canonicals[0], url):
        item['issues'].append('canonical_mismatch')
    if doc.noindex or {'noindex', 'none'} & set(re.split(r'[\s,]+', item.get('x_robots_tag', '').lower())):
        item['issues'].append('noindex_in_sitemap')
    if not doc.h1 or not item['visible_text_characters']:
        item['issues'].append('missing_html_body_or_h1')
    for root in doc.schemas:
        for node in schema_nodes(root):
            if node.get('parse_error'): item['issues'].append('invalid_json_ld')
            if node.get('@type') != 'JobPosting': continue
            if '/jobs/' not in url: item['issues'].append('jobposting_outside_notice')
            end = node.get('validThrough')
            if end:
                try:
                    dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                    if dt.tzinfo is None: item['issues'].append('unverified_expiry_timezone')
                    elif dt < datetime.now(timezone.utc): item['issues'].append('expired_jobposting')
                except (ValueError, TypeError): item['issues'].append('invalid_expiry')
    for href in doc.links:
        target = encoded_url(urljoin(url, href).split('#', 1)[0])
        if in_scope(target) and (target.endswith('.html') or urlparse(target).path.endswith('/')):
            links.add(target)
    return item, links


def robots_result(item, data, urls):
    result = {'url': ROBOTS, 'status': item['status'], 'blocked': [], 'interpretation': 'unverified'}
    if item['status'] == 404:
        result['interpretation'] = 'no_host_root_rules_observed_not_a_crawl_block'
    elif item['status'] == 200 and data is not None:
        text = data.decode('utf-8', 'replace')
        result['body'] = text
        parser = RobotFileParser(ROBOTS); parser.parse(text.splitlines())
        result['interpretation'] = 'standard_parser_check_requires_review_for_advanced_rules'
        result['blocked'] = [{'agent': agent, 'url': url} for agent in AGENTS for url in urls if not parser.can_fetch(agent, url)]
    return result


def retry_observations(rows, loader):
    """One bounded retry of transport failures, preserving the first observation.

    Reuse SupportPick's validated release-check approach; never retry a 404 or
    disguise invalid content as a successful response.
    """
    observations = []
    for index, row in enumerate(rows):
        retryable = row['status'] in TRANSIENT or (
            row['status'] == 'unverified' and row.get('error') in
            {'URLError', 'TimeoutError', 'ConnectionError', 'RemoteDisconnected', 'OSError'})
        if not retryable: continue
        second, _ = examine(row['url'], loader)
        observations.append({'url': row['url'], 'initial_status': row['status'],
                             'initial_error': row.get('error'), 'retry_status': second['status'],
                             'recovered': second['status'] == 200 and not second['issues']})
        rows[index] = second
    return observations


def run(all_urls=False, workers=4, loader=fetch):
    started = time.monotonic()
    sm, data = loader(BASE + 'sitemap.xml')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'sitemap': sm,
              'mode': 'all' if all_urls else 'representative', 'errors': [], 'warnings': [],
              'limits': ['HTTP/XML/HTML audit only, not Google/Naver indexing proof',
                         'Network errors remain unverified, not proof of site outage or bot blocking',
                         'No JavaScript, SDK, advertisements, collection or delivery is executed']}
    if sm['status'] != 200 or data is None:
        if sm['status'] == 'unverified':
            report['warnings'].append('sitemap_http_unverified')
        else:
            report['errors'].append('sitemap_http_' + str(sm['status']))
        return report
    try: urls = sitemap_urls(data)
    except (ET.ParseError, ValueError) as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error)); return report
    sm['url_count'] = len(urls); sm['xml_valid'] = True
    for path in SAMPLES:
        if BASE + path not in urls:
            report['errors'].append('required_page_missing_from_sitemap: ' + BASE + path)
    ri, rd = loader(ROBOTS)
    report['robots'] = robots_result(ri, rd, urls + [BASE + 'sitemap.xml'])
    if report['robots']['blocked']: report['errors'].append('host_root_robots_disallows_project_urls')
    if ri['status'] not in (200, 404): report['warnings'].append('host_root_robots_unverified')
    fi, fd = loader(BASE + 'alio.json')
    report['public_feed'] = fi
    feed_ids = set()
    if fi['status'] == 200 and fd:
        try:
            feed = json.loads(fd)
            feed_ids = {str(p.get('id')) for p in feed.get('posts', []) if re.fullmatch(r'a[0-9]+', str(p.get('id', '')))}
            missing = sorted(pid for pid in feed_ids if BASE + 'jobs/' + pid + '.html' not in urls)
            report['public_feed'].update(notice_count=len(feed_ids), missing_sitemap_ids=missing)
            if missing: report['errors'].append('current_notices_missing_from_sitemap')
        except (ValueError, TypeError, AttributeError): report['errors'].append('public_feed_invalid_json_or_shape')
    else: report['warnings'].append('public_feed_unverified')
    selected = urls if all_urls else [BASE + path for path in SAMPLES if BASE + path in urls]
    if not all_urls and feed_ids: selected += [BASE + 'jobs/' + sorted(feed_ids)[-1] + '.html']
    rows, linked = [], set()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        futures = {pool.submit(examine, url, loader): url for url in selected}
        for future in as_completed(futures):
            row, links = future.result(); rows.append(row); linked.update(links)
            if all_urls and len(rows) % 100 == 0:
                print(json.dumps({'completed': len(rows), 'total': len(selected)}, ensure_ascii=False), flush=True)
    # Additional ordinary HTML links are checked once for status; noindex is valid
    # for utility pages outside the sitemap. Do not follow external/blog links.
    extra = sorted(linked - set(urls)) if all_urls else []
    extra_rows = []
    for url in extra[:100]:
        row, _ = loader(url); extra_rows.append(row)
    report['transport_retries'] = retry_observations(rows, loader)
    report['additional_internal_html'] = extra_rows
    if len(extra) > 100: report['warnings'].append('additional_internal_html_audit_limit_reached')
    for row in rows:
        if row['status'] == 'unverified': report['warnings'].append('unverified_url: ' + row['url'])
        elif row['status'] != 200: report['errors'].append('http_' + str(row['status']) + ': ' + row['url'])
        report['errors'].extend(issue + ': ' + row['url'] for issue in row['issues'])
    for row in extra_rows:
        if row['status'] == 'unverified': report['warnings'].append('unverified_linked_url: ' + row['url'])
        elif row['status'] != 200: report['errors'].append('linked_http_' + str(row['status']) + ': ' + row['url'])
    titles = Counter(row.get('title') for row in rows if row.get('title'))
    descriptions = Counter(row.get('description') for row in rows if row.get('description'))
    report.update(pages=sorted(rows, key=lambda row: row['url']), checked_urls=len(rows),
                  status_counts=dict(Counter(str(row['status']) for row in rows)),
                  duplicate_title_groups=sum(count > 1 for count in titles.values()),
                  duplicate_description_groups=sum(count > 1 for count in descriptions.values()),
                  seconds=round(time.monotonic() - started, 2))
    if report['duplicate_title_groups']: report['warnings'].append('duplicate_titles_require_content_review')
    if report['duplicate_description_groups']: report['warnings'].append('duplicate_descriptions_require_content_review')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-urls', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', type=Path, default=Path('public-search-report.json'))
    args = parser.parse_args()
    result = run(args.all_urls, args.workers)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('pages', 'additional_internal_html')}, ensure_ascii=False, indent=2))
    # 2 means incomplete/review required; it must not be described as a site outage.
    raise SystemExit(1 if result['errors'] else 2 if result['warnings'] else 0)


if __name__ == '__main__': main()
