import copy
import html
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import quote

import sitegen
from scripts import build_sitemap
from scripts.build_public_site import complete_public_navigation
from scripts.search_readiness import BASE, Page, inspect, normalize_duplicate_metadata, remove_unverified_archived_schema


def document(relative, title, description='페이지 안내', body='<h1>본문</h1>', robots=''):
    url = BASE + ('' if relative == 'index.html' else relative)
    return ('<html><head><title>' + html.escape(title) + '</title>'
            '<link rel="canonical" href="' + url + '">'
            '<meta name="description" content="' + html.escape(description, quote=True) + '">'
            + robots + '</head><body>' + body + '</body></html>')


def write_page(root, relative, **kwargs):
    p = root / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(document(relative, **kwargs), encoding='utf-8')
    return p


def sitemap(root, paths):
    (root / 'sitemap.xml').write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + ''.join('<url><loc>' + BASE + p + '</loc></url>' for p in paths)
        + '</urlset>', encoding='utf-8')


class SearchReadinessTests(unittest.TestCase):
    def test_archived_search_and_share_dates_do_not_claim_verified_application_deadlines(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = '<h1>공고 원문</h1><p>보존할 본문과 공식 링크</p>'
            for pid in ('a1', 'a2'):
                p = write_page(root, 'jobs/' + pid + '.html', title='채용',
                               description='기관 | 접수마감 2026-11-09 23:59', body=body)
                p.write_text(p.read_text().replace('</head>',
                    '<meta property="og:description" content="접수마감 2026-11-09 23:59">'
                    "<meta name='twitter:description' content='접수마감 2026-11-09 23:59'>"
                    '<meta name="unrelated" content="접수마감"></head>'))
            complete_public_navigation(root, {'a2'})
            archived = (root / 'jobs/a1.html').read_text()
            current = (root / 'jobs/a2.html').read_text()
            expected = '보관 당시 종료일 · 접수기간 미확인 2026-11-09 23:59'
            self.assertEqual(archived.count(expected), 3)
            self.assertIn(body, archived)
            self.assertIn('<meta name="unrelated" content="접수마감">', archived)
            self.assertEqual(current.count('접수마감 2026-11-09 23:59'), 3)

    def test_prerender_links_to_existing_internal_notice_without_changing_feed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'jobs').mkdir()
            (root / 'jobs/a1.html').write_text('existing')
            (root / 'index.html').write_text('<ul><!--STATIC-LIST-->old<!--/STATIC-LIST--></ul>')
            post = dict(id='a1', type='j', alio=True, title='<직무> & 채용 공고', org='기관',
                        due='2099-01-01T18:00:00+09:00', url='https://official.example/notice/1')
            before = copy.deepcopy(post)
            with patch.object(sitegen, 'ROOT', root):
                sitegen.prerender_index([post], datetime(2026, 11, 4, tzinfo=timezone.utc))
            result = (root / 'index.html').read_text()
            self.assertIn(BASE + 'jobs/a1.html', result)
            self.assertNotIn('href="https://official.example', result)
            self.assertIn('&lt;직무&gt;', result)
            self.assertEqual(post, before)

    def test_missing_and_malformed_notice_ids_keep_official_fallback(self):
        with TemporaryDirectory() as tmp, patch.object(sitegen, 'ROOT', Path(tmp)):
            for pid in ['a9', '../../index', 'a1?x=2']:
                self.assertEqual(sitegen.job_href(dict(id=pid, type='j', alio=True, url='https://official.example/notice')), 'https://official.example/notice')

    def test_same_title_notices_are_distinct_without_editing_body_or_schema(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = '<h1>같은 제목 &amp; 기관</h1><p>실제 원문 유지</p><script type="application/ld+json">' + json.dumps({'@type': 'JobPosting', 'title': 'same'}) + '</script>'
            files = [write_page(root, 'jobs/' + pid + '.html', title='같은 제목 & 기관', description='같은 설명', body=body) for pid in ['a1', 'a2']]
            self.assertEqual(normalize_duplicate_metadata(root), 2)
            docs = [Page(p.read_text()) for p in files]
            self.assertNotEqual(docs[0].title, docs[1].title)
            self.assertNotEqual(docs[0].descriptions, docs[1].descriptions)
            self.assertEqual(docs[0].schemas, docs[1].schemas)
            for p in files:
                self.assertEqual(p.read_text().split('</head>')[1], '<body>' + body + '</body></html>')

    def test_metadata_normalization_is_idempotent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = [write_page(root, 'jobs/' + pid + '.html', title='같은 제목') for pid in ['a1', 'a2']]
            normalize_duplicate_metadata(root)
            before = [p.read_bytes() for p in files]
            self.assertEqual(normalize_duplicate_metadata(root), 0)
            self.assertEqual([p.read_bytes() for p in files], before)

    def test_noindex_sitemap_conflict_is_detected_and_empty_home_remains_valid(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_page(root, 'index.html', title='홈', description='현재 모집 공고 확인')
            write_page(root, 'kakao.html', title='문구 도구', description='사용 도구', robots='<meta name="robots" content="noindex,follow">')
            sitemap(root, ['', 'kakao.html'])
            self.assertTrue(any('noindex URL in sitemap' in e for e in inspect(root)['errors']))
            sitemap(root, [''])
            result = inspect(root)
            self.assertFalse(result['errors'])
            self.assertEqual(result['static_homepage_job_links'], 0)

    def test_encoded_korean_sitemap_url_matches_same_canonical(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_page(root, 'index.html', title='홈', description='홈 설명')
            write_page(root, 'org-기관.html', title='기관', description='기관 안내')
            sitemap(root, ['', quote('org-기관.html')])
            self.assertFalse(inspect(root)['errors'])

    def test_expired_jobposting_is_rejected_without_hiding_the_page(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = {'@type': 'JobPosting', 'validThrough': '2020-01-01T18:00:00+09:00'}
            page = write_page(root, 'jobs/a1.html', title='보관 공고', body='<h1>보관 공고</h1><script type="application/ld+json">' + json.dumps(schema) + '</script>')
            sitemap(root, ['jobs/a1.html'])
            self.assertTrue(any('expired JobPosting' in e for e in inspect(root)['errors']))
            self.assertTrue(page.exists())

    def test_archived_unverified_schema_removed_while_body_and_current_metadata_survive(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = '<h1>보관 공고</h1><p>보존할 본문</p>'
            schemas = '<script type="application/ld+json">{"@type":"JobPosting","validThrough":"2099-01-01"}</script><script type="application/ld+json">{"@type":"BreadcrumbList"}</script>'
            archived = write_page(root, 'jobs/a1.html', title='보관', body=body + schemas)
            current = write_page(root, 'jobs/a2.html', title='현재', body=body + schemas)
            original_current = current.read_bytes()
            self.assertEqual(remove_unverified_archived_schema(root, {'a2'}), 1)
            self.assertIn(body, archived.read_text())
            self.assertEqual(Page(archived.read_text()).schemas, [{'@type': 'BreadcrumbList'}])
            self.assertEqual(current.read_bytes(), original_current)

    def test_rebuild_does_not_assign_today_to_unverified_content(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'jobs').mkdir()
            (root / 'jobs/a1.html').write_text('<h1>보관</h1>')
            (root / 'guides').mkdir()
            (root / 'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>' + BASE + '</loc><lastmod>2099-01-01</lastmod></url></urlset>')
            with patch.object(build_sitemap, 'ROOT', root), patch.object(build_sitemap, 'JOBS', root / 'jobs'), patch.object(build_sitemap, 'SITEMAP', root / 'sitemap.xml'):
                build_sitemap.main()
                first = (root / 'sitemap.xml').read_bytes()
                self.assertNotIn(b'lastmod', first)
                build_sitemap.main()
                self.assertEqual((root / 'sitemap.xml').read_bytes(), first)
            with patch.object(sitegen, 'ROOT', root):
                a = sitegen.gen_sitemap(datetime(2026, 11, 4, tzinfo=timezone.utc))
                b = sitegen.gen_sitemap(datetime(2026, 11, 5, tzinfo=timezone.utc))
                self.assertEqual(a, b)
                self.assertNotIn('lastmod', a)


if __name__ == '__main__':
    unittest.main()
