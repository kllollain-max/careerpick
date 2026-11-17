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

    def test_official_future_windows_excluded_only_when_original_identity_matches(self):
        import copy
        east = dict(row('a307149', due='2026-12-01', emp=['정규직'], n='101'),
                    alio=True, org='한국동서발전(주)', title='2027년 상반기 신입직원')
        credit = dict(row('a307067', due='2026-12-01', emp=['정규직'], n='6'),
                      alio=True, org='신용보증재단중앙회', title='2026년 신입직원')
        future_dental = dict(row('a306925', due='2027-01-22', emp=['정규직'], n='48'),
                             alio=True, org='서울대학교치과병원', title='전공의 인턴')
        current = dict(row('a306799', due='2026-11-23', emp=['정규직'], n='97'),
                       alio=True, org='국립중앙의료원', title='신규 간호사')
        feed = {'posts': [east, credit, future_dental, current]}
        before = copy.deepcopy(feed)
        windows = {
            'a307149': dict(organization=east['org'], title=east['title'],
                            source_end_date='2026-12-01', application_start='2026-11-24'),
            'a307067': dict(organization=credit['org'], title=credit['title'],
                            source_end_date='2026-12-01', application_start='2026-11-18'),
            'a306925': dict(organization=future_dental['org'], title=future_dental['title'],
                            source_end_date='2027-01-22',
                            application_start='2027-01-18T09:00:00+09:00'),
        }
        report = shortlist(feed, date(2026, 11, 17), verified_windows=windows)
        self.assertEqual([x['id'] for x in report['top']], ['a306799'])
        self.assertEqual(report['excluded']['official_reception_not_open'], 3)
        self.assertEqual(feed, before)
        # Start DATE is confirmed, but the actual opening CLOCK is unknown.
        on_start = shortlist(feed, date(2026, 11, 24), verified_windows=windows)
        self.assertIn('a307149', [x['id'] for x in on_start['top']])
        self.assertIn('Date-only evaluation' , ' '.join(on_start['limitations']))
        # A revised notice is never suppressed by stale evidence.
        changed = dict(east, title='수정 공고')
        stale = shortlist({'posts': [changed]}, date(2026, 11, 17),
                          verified_windows=windows)
        self.assertEqual(len(stale['top']), 1)
        changed = dict(east, due='2026-12-02T23:59:00+09:00')
        stale = shortlist({'posts': [changed]}, date(2026, 11, 17),
                          verified_windows=windows)
        self.assertEqual(len(stale['top']), 1)
        changed = dict(east, alio=False)
        stale = shortlist({'posts': [changed]}, date(2026, 11, 17),
                          verified_windows=windows)
        self.assertEqual(len(stale['top']), 1)

    def test_separate_regular_review_queue_holds_ambiguous_titles(self):
        # Metadata-level queue only: not proof of open recruitment or seats.
        feed={'posts': [
            dict(row('a1', emp=['정규직'], n='97'), org='의료원'),
            dict(row('a2', emp=['정규직'], n='2'), org='국민연금공단'),
            dict(row('a3', emp=['정규직'], n='40', due='2026-12-01'),
                 alio=True, org='발전기관', title='발전 신입'),
            dict(row('a4', emp=['정규직', '무기계약직'], n='80'), org='철도공단'),
            dict(row('a5', emp=['정규직'], n='90'), title='위촉직 임시 모집'),
            dict(row('a6', emp=['정규직'], n='3'), org='철도공사'),
        ]}
        windows={'a3': {'organization':'발전기관', 'title':'발전 신입',
                        'source_end_date':'2026-12-01',
                        'application_start':'2026-11-24'}}
        report=shortlist(feed, date(2026,11,17),verified_windows=windows)
        review=report['regular_review_candidates']
        self.assertEqual([x['id'] for x in review],['a6','a2','a1'])
        self.assertEqual(report['regular_review_candidate_rows'],3)
        self.assertEqual(report['regular_title_conflict_hold_ids'],['a5'])
        self.assertEqual(report['excluded']['official_reception_not_open'],1)
        self.assertIn('a4',[x['id'] for x in report['top']])
        self.assertTrue(all(x['official_reception_status']=='unverified' for x in review))
        self.assertTrue(all(x['official_position_and_qualification_review']=='pending' for x in review))
        self.assertTrue(any('UNVERIFIED' in x for x in report['limitations']))
        short=shortlist(feed, date(2026,11,17),limit=2,verified_windows=windows)
        self.assertEqual(len(short['regular_review_candidates']),2)

    def test_no_fake_popularity_or_count(self):
        self.assertIsNone(seat_count('10명'))
        self.assertIsNone(seat_count('-1'))
        result=shortlist({'posts':[row('a1',n='10명')]},date(2026,11,9))
        self.assertTrue(any('Not a search-volume' in x for x in result['limitations']))
        self.assertIsNone(result['top'][0]['reported_seats'])

if __name__ == '__main__': unittest.main()
