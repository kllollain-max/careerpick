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
    def test_mixed_employment_seats_are_not_promoted_as_regular_only(self):
        # a306815 style: four seats shared by open-position and internship tracks.
        # a306913 style: 23 total, of which 9 regular / 14 other positions.
        feed={'posts':[
            row('a1',emp=['정규직', '인턴'],n='4'),
            row('a2',emp=['무기계약직', '정규직'],n='23'),
            row('a3',emp=['정규직'],n='3'),
            row('a4',emp=['인턴'],n='80'),
        ]}
        result=shortlist(feed,date(2026,11,17))
        entries={x['id']:x for x in result['top']}
        self.assertEqual(result['top'][0]['id'],'a3')
        self.assertTrue(entries['a3']['regular_only_classified'])
        self.assertTrue(entries['a1']['permanent_classified'])
        self.assertFalse(entries['a1']['regular_only_classified'])
        self.assertTrue(entries['a1']['mixed_employment_with_regular'])
        self.assertEqual(entries['a2']['reported_seats'],23)
        self.assertFalse(entries['a2']['regular_only_classified'])
        self.assertEqual(entries['a2']['triage_score'],23)
        self.assertFalse(entries['a4']['mixed_employment_with_regular'])
        self.assertTrue(any('Mixed-employment' in x for x in result['limitations']))
    def test_single_regular_classification_does_not_infer_source_count_validity(self):
        result=shortlist({'posts':[row('a1', emp=['정규직'],n='15')]},date(2026,11,17))
        self.assertTrue(result['top'][0]['regular_only_classified'])
        self.assertEqual(result['top'][0]['reported_seats'],15)
        self.assertTrue(any('not independently confirmed' in x for x in result['limitations']))

    def test_no_fake_popularity_or_count(self):
        self.assertIsNone(seat_count('10명'))
        self.assertIsNone(seat_count('-1'))
        result=shortlist({'posts':[row('a1',n='10명')]},date(2026,11,9))
        self.assertTrue(any('Not a search-volume' in x for x in result['limitations']))
        self.assertIsNone(result['top'][0]['reported_seats'])

if __name__ == '__main__': unittest.main()
