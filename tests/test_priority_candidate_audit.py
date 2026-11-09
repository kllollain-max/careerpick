import unittest
from datetime import date
from scripts.priority_candidate_audit import shortlist, seat_count

def row(identity, due='2026-12-01', emp=None, n='20', url='https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=3'):
    return {'id':identity,'title':'공식 채용','org':'기관','due':due,'url':url,'emp':emp or [],'n':n}

class PriorityAuditTests(unittest.TestCase):
    def test_priority_and_expiry(self):
        feed={'posts':[row('a1',emp=['정규직'],n='3'),row('a2',emp=['정규직'],n='20'),
                       row('a3',emp=['계약직'],n='80'),row('a4',due='2026-01-01')]}
        result=shortlist(feed,date(2026,11,9))
        self.assertEqual([x['id'] for x in result['top']],['a2','a1','a3'])
        self.assertEqual(result['excluded']['expired'],1)
        self.assertEqual(result['top'][0]['reported_seats'],20)
    def test_unknown_and_misleading_sources_excluded(self):
        feed={'posts':[row('a1',due='unknown'),row('a2',url='https://evil.example/apply'),
                       row('a3',n='수십 명'),row('a3')]}
        result=shortlist(feed,date(2026,11,9))
        self.assertEqual(len(result['top']),1)
        self.assertIsNone(result['top'][0]['reported_seats'])
        self.assertEqual(result['excluded']['duplicate_or_bad_id'],1)
        self.assertEqual(result['excluded']['unknown_deadline'],1)
        self.assertEqual(result['excluded']['unverified_source'],1)
    def test_no_fake_popularity_or_count(self):
        self.assertIsNone(seat_count('10명'))
        self.assertIsNone(seat_count('-1'))
        result=shortlist({'posts':[row('a1',n='10명')]},date(2026,11,9))
        self.assertTrue(any('Not a search-volume' in x for x in result['limitations']))
        self.assertIsNone(result['top'][0]['reported_seats'])

if __name__ == '__main__': unittest.main()
