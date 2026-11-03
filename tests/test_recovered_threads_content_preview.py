import unittest
from datetime import date
from scripts.threads_content_preview import generate, official_url, checked_job
from scripts.threads_metrics_preview import parse_insights, collect_post_insights
import io

TODAY = date(2026, 10, 29)
JOB = {'verified': True, 'org': '예시공단', 'title': '전산직 채용',
       'due': '2026-11-10', 'url': 'https://job.alio.go.kr/recruitview.do?idx=123',
       'count': 12, 'regular': True}

class PreviewTests(unittest.TestCase):
    def test_four_types_and_facts(self):
        result = [generate(h, [JOB], TODAY, 'seed') for h in (8, 12, 16, 20)]
        self.assertEqual([r['type'] for r in result], ['job', 'conversation', 'tips', 'strategy'])
        for r in (result[0], result[3]):
            for value in ('예시공단', '전산직 채용', '12명', '2026-11-10', JOB['url']):
                self.assertIn(value, r['body'])
            self.assertLessEqual(len(r['body']), 500)
        self.assertEqual(result[0]['replies'], [])

    def test_no_unverified_closed_or_cancelled(self):
        for change in ({'verified': False}, {'due': '2026-10-29'}, {'title': '채용 취소'}, {'count': True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                checked_job(dict(JOB, **change), TODAY)
        good = generate(8, [dict(JOB, verified=False), JOB], TODAY, 1)
        self.assertIn('예시공단', good['body'])

    def test_url_validation(self):
        self.assertTrue(official_url(JOB['url']))
        for url in ('http://job.alio.go.kr/recruitview.do?idx=1', 'https://job.alio.go.kr.evil.test/recruitview.do?idx=1', 'https://job.alio.go.kr/recruitview.do?idx=x', 'https://user@job.alio.go.kr/recruitview.do?idx=1'):
            self.assertFalse(official_url(url))

    def test_recent_hook_avoided_and_fallback(self):
        first = generate(8, [JOB], TODAY, 12)['body'].splitlines()[0]
        second = generate(8, [JOB], TODAY, 12, [first])['body'].splitlines()[0]
        self.assertNotEqual(first, second)
        with self.assertRaises(ValueError):
            generate(8, [], TODAY, 1)

    def test_collector_get_is_read_only(self):
        def opener(request, timeout):
            self.assertEqual(request.get_method(), 'GET')
            self.assertIn('/123/insights?', request.full_url)
            self.assertNotIn('secret', request.full_url)
            self.assertEqual(timeout, 15)
            return io.BytesIO(b'{"data": [{"name": "views", "values": [{"value": 8}]}]}')
        self.assertEqual(collect_post_insights('123', 'secret', opener)['metrics']['views'], 8)

    def test_metrics_unknown_not_zero(self):
        data = {'data': [{'name':'views', 'values':[{'value':23}]}, {'name':'likes', 'values':[{'value':0}]}]}
        result = parse_insights(data, '123', '2026-10-29T00:00:00Z')
        self.assertEqual(result['metrics']['views'], 23)
        self.assertEqual(result['metrics']['likes'], 0)
        self.assertIsNone(result['metrics']['replies'])
        self.assertIsNone(result['site_visits'])
        with self.assertRaises(ValueError):
            parse_insights({}, '123')

if __name__ == '__main__':
    unittest.main()
