import json
import unittest

from scripts import check_search_public as audit


def xml(paths):
    return ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + ''.join('<url><loc>' + audit.BASE + p + '</loc></url>' for p in paths)
            + '</urlset>').encode()


def page(url, robots='', schema=''):
    return ('<html><head><title>' + url + '</title><meta name="description" content="안내">'
            '<link rel="canonical" href="' + url + '">' + robots + '</head>'
            '<body><h1>공개 본문</h1><p>공식 원문 확인 안내</p>' + schema + '</body></html>').encode()


class PublicSearchAuditTests(unittest.TestCase):
    def loader(self, paths=None, robots_status=404, robots=b'', feed=None):
        paths = audit.SAMPLES if paths is None else paths
        calls = []
        def load(url):
            calls.append(url)
            row = {'url': url, 'final_url': url, 'status': 200, 'content_type': 'text/html'}
            if url == audit.BASE + 'sitemap.xml': return row, xml(paths)
            if url == audit.ROBOTS: return dict(row, status=robots_status), robots
            if url == audit.BASE + 'alio.json': return row, json.dumps({'posts': feed or []}).encode()
            return row, page(url)
        return load, calls

    def test_rejects_foreign_and_malformed_sitemap_before_crawling(self):
        bad = [b'<urlset/>', xml(['', '']), xml(['../private.html']),
               xml(['']).replace(audit.BASE.encode(), b'https://foreign.example/')]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ValueError): audit.sitemap_urls(data)

    def test_root_robots_is_used_and_missing_file_does_not_mean_block(self):
        load, calls = self.loader()
        report = audit.run(loader=load)
        self.assertFalse(report['errors'])
        self.assertEqual(report['robots']['status'], 404)
        self.assertIn('not_a_crawl_block', report['robots']['interpretation'])
        self.assertNotIn(audit.BASE + 'robots.txt', calls)

    def test_actual_root_disallow_is_detected(self):
        load, _ = self.loader(robots_status=200, robots=b'User-agent: *\nDisallow: /careerpick/\n')
        report = audit.run(loader=load)
        self.assertIn('host_root_robots_disallows_project_urls', report['errors'])

    def test_network_failure_remains_unverified(self):
        base, _ = self.loader()
        def load(url):
            if url == audit.BASE: return {'url': url, 'status': 'unverified', 'error': 'TimeoutError'}, None
            return base(url)
        report = audit.run(loader=load)
        self.assertFalse(report['errors'])
        self.assertEqual(report['status_counts']['unverified'], 1)
        self.assertTrue(report['warnings'])

    def test_headers_and_meta_noindex_conflict_with_sitemap(self):
        for field in ['meta', 'header']:
            def load(url):
                return ({'url': url, 'status': 200, 'content_type': 'text/html',
                         'x_robots_tag': 'noindex' if field == 'header' else ''},
                        page(url, '<meta name="robots" content="noindex">' if field == 'meta' else ''))
            row, _ = audit.examine(audit.BASE, load)
            self.assertIn('noindex_in_sitemap', row['issues'])

    def test_new_feed_notice_missing_from_sitemap_is_reported(self):
        load, _ = self.loader(feed=[{'id': 'a999'}])
        report = audit.run(loader=load)
        self.assertEqual(report['public_feed']['missing_sitemap_ids'], ['a999'])
        self.assertIn('current_notices_missing_from_sitemap', report['errors'])

    def test_different_canonical_and_expired_markup_are_detected(self):
        url = audit.BASE + 'jobs/a1.html'
        source = page(url, schema='<script type="application/ld+json">{"@type":"JobPosting","validThrough":"2020-01-01T00:00:00+09:00"}</script>')
        source = source.replace(('href="' + url).encode(), ('href="' + audit.BASE).encode())
        row, _ = audit.examine(url, lambda _: ({'url': url, 'status': 200, 'content_type': 'text/html'}, source))
        self.assertIn('canonical_mismatch', row['issues'])
        self.assertIn('expired_jobposting', row['issues'])

    def test_scope_excludes_queries_and_host_root_and_private_hosts(self):
        for url in ['https://127.0.0.1/', 'https://kllollain-max.github.io/',
                    audit.BASE + '?refresh=1', audit.BASE + '../other/', audit.BASE + '%2e%2e/private']:
            self.assertFalse(audit.in_scope(url))
        self.assertTrue(audit.in_scope(audit.BASE + 'guides/'))

    def test_missing_policy_page_is_not_silently_skipped(self):
        load, _ = self.loader(paths=[p for p in audit.SAMPLES if p != 'privacy.html'])
        report = audit.run(loader=load)
        self.assertIn('required_page_missing_from_sitemap: ' + audit.BASE + 'privacy.html', report['errors'])

    def test_job_only_robots_block_is_detected(self):
        load, _ = self.loader(paths=list(audit.SAMPLES) + ['jobs/a1.html'], robots_status=200,
                              robots=b'User-agent: Googlebot\nDisallow: /careerpick/jobs/\n')
        report = audit.run(loader=load)
        self.assertTrue(any(row['url'].endswith('jobs/a1.html') for row in report['robots']['blocked']))

    def test_unverified_sitemap_does_not_become_an_observed_http_error(self):
        report = audit.run(loader=lambda url: ({'url': url, 'status': 'unverified', 'error': 'TimeoutError'}, None))
        self.assertFalse(report['errors'])
        self.assertEqual(report['warnings'], ['sitemap_http_unverified'])

    def test_transient_http_response_is_retried_once_and_recorded(self):
        rows = [{'url': audit.BASE, 'status': 503, 'issues': []}]
        load, calls = self.loader()
        observations = audit.retry_observations(rows, load)
        self.assertEqual(calls, [audit.BASE])
        self.assertEqual(rows[0]['status'], 200)
        self.assertEqual(observations[0]['initial_status'], 503)
        self.assertTrue(observations[0]['recovered'])

    def test_missing_page_is_not_retried_or_marked_recovered(self):
        rows = [{'url': audit.BASE, 'status': 404, 'issues': []}]
        observations = audit.retry_observations(rows, lambda _: self.fail('404 must not be retried'))
        self.assertFalse(observations)
        self.assertEqual(rows[0]['status'], 404)

    def test_unicode_links_match_the_encoded_sitemap_without_duplicate_fetches(self):
        url = audit.BASE + 'org-한국기관.html'
        encoded = audit.encoded_url(url)
        self.assertNotIn('한국', encoded)
        self.assertEqual(audit.encoded_url(encoded), encoded)
        source = page(audit.BASE) + ('<a href="' + url + '">기관</a>').encode()
        _, links = audit.examine(audit.BASE, lambda _: ({'url': audit.BASE, 'status': 200, 'content_type': 'text/html'}, source))
        self.assertIn(encoded, links)


if __name__ == '__main__': unittest.main()
