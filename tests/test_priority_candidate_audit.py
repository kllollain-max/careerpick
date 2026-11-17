import unittest
from datetime import date
from scripts.priority_candidate_audit import shortlist, seat_count

def row(identity, due='2026-12-01', emp=None, n='20', url='https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=3'):
    return {'id':identity,'title':'공식 채용','org':'기관','due':due,'url':url,'emp':emp or [],'n':n}

class PriorityAuditTests(unittest.TestCase):
    def test_official_contract_and_until_filled_evidence_are_held_from_regular_queue(self):
        posts=[dict(row('a1',emp=['정규직']),alio=True),dict(row('a2',emp=['정규직']),alio=True)]
        proof={p['id']:{'organization':p['org'],'title':p['title'],'source_end_date':p['due']} for p in posts}
        proof['a1'].update(confirmed_employment='계약직',source_employment=['정규직'])
        proof['a2']['application_status_unconfirmed']=True
        result=shortlist({'posts':posts},date(2026,11,18),verified_windows=proof)
        self.assertEqual(result['top'],[])
        self.assertEqual(result['excluded']['official_employment_conflict'],1)
        self.assertEqual(result['excluded']['official_current_status_unconfirmed'],1)
        proof['a1']['title']='수정 공고';proof['a2']['source_end_date']='2026-12-02'
        result=shortlist({'posts':posts},date(2026,11,18),verified_windows=proof)
        self.assertEqual(len(result['top']),2)

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

    def test_realtime_exact_official_cutoff_excludes_same_day_after_close(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        kst = ZoneInfo('Asia/Seoul')
        post = dict(row('a306662', due='2026-11-18', emp=['정규직'], n='50'),
                    alio=True, org='한국원자력의학원', title='신규간호사')
        proof = {'a306662': dict(organization='한국원자력의학원',
                                title='신규간호사', source_end_date='2026-11-18',
                                application_start='2026-11-03',
                                application_cutoff='2026-11-18T17:00:00+09:00')}
        feed = {'posts': [post]}
        before = shortlist(feed, date(2026, 11, 18), verified_windows=proof,
                           as_of_instant=datetime(2026, 11, 18, 16, 59, tzinfo=kst))
        self.assertEqual([x['id'] for x in before['top']], ['a306662'])
        at_close = shortlist(feed, date(2026, 11, 18), verified_windows=proof,
                             as_of_instant=datetime(2026, 11, 18, 17, 0, tzinfo=kst))
        self.assertEqual(at_close['excluded']['official_reception_closed'], 1)
        self.assertEqual(at_close['regular_review_candidate_rows'], 0)
        # Historical --as-of runs have only a date; no invented same-day clock.
        historical = shortlist(feed, date(2026, 11, 18), verified_windows=proof)
        self.assertEqual(len(historical['top']), 1)
        # Stale official evidence must NEVER suppress a changed source.
        changed = dict(post, title='수정 공고')
        self.assertEqual(len(shortlist({'posts':[changed]}, date(2026,11,18),
                                       verified_windows=proof,
                                       as_of_instant=datetime(2026,11,18,17,0,tzinfo=kst))['top']), 1)
        with self.assertRaises(ValueError):
            shortlist(feed, date(2026,11,18), verified_windows=proof,
                      as_of_instant=datetime(2026,11,18,17,0))

    def test_clock_aware_opening_never_infers_date_only_close(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        kst = ZoneInfo('Asia/Seoul')
        post = dict(row('a306925', due='2027-01-22', emp=['정규직'], n='48'),
                    alio=True, org='서울대학교치과병원', title='치과 인턴')
        proof = {'a306925': dict(organization='서울대학교치과병원', title='치과 인턴',
                                source_end_date='2027-01-22',
                                application_start='2027-01-18T09:00:00+09:00')}
        feed = {'posts':[post]}
        early = shortlist(feed,date(2027,1,18),verified_windows=proof,
                          as_of_instant=datetime(2027,1,18,8,59,tzinfo=kst))
        self.assertEqual(early['excluded']['official_reception_not_open'],1)
        opened = shortlist(feed,date(2027,1,18),verified_windows=proof,
                           as_of_instant=datetime(2027,1,18,9,0,tzinfo=kst))
        self.assertEqual(len(opened['top']),1)
        date_only = {'a306925': {**proof['a306925'],
                                 'application_start':'2027-01-18',
                                 'application_end_date':'2027-01-22'}}
        late = shortlist(feed,date(2027,1,22),verified_windows=date_only,
                         as_of_instant=datetime(2027,1,22,23,58,tzinfo=kst))
        self.assertEqual(len(late['top']),1)
        self.assertNotIn('official_reception_closed',late['excluded'])

    def test_current_verified_same_notice_only_suppresses_regular_review_queue(self):
        # These are synthetic notices; the production mapping is populated
        # exclusively by notice_review.load with current feed+detail fingerprints
        # and identical announcement AND job-duty original SHA-256.
        original = dict(row('a1', emp=['정규직'], n='20'), org='같은기관', title='모집A')
        same = dict(row('a2', emp=['정규직'], n='20'), org='같은기관', title='모집A')
        distinct_one = dict(row('a3', emp=['정규직'], n='1'), org='다른기관', title='독립모집1')
        distinct_two = dict(row('a4', emp=['정규직'], n='1'), org='다른기관', title='독립모집2')
        feed = {'posts': [original, same, distinct_one, distinct_two]}
        before = shortlist(feed, date(2026, 11, 18))
        self.assertEqual(len(before['regular_review_candidates']), 4)
        after = shortlist(feed, date(2026, 11, 18),
                          verified_duplicate_representatives={'a2': 'a1'})
        self.assertEqual(after['eligible_rows'], before['eligible_rows'])
        self.assertEqual([r['id'] for r in after['top']],
                         [r['id'] for r in before['top']])
        self.assertEqual({r['id'] for r in after['regular_review_candidates']},
                         {'a1', 'a3', 'a4'})
        self.assertEqual(after['regular_review_verified_duplicate_exclusions'],
                         [{'id': 'a2', 'representative_id': 'a1'}])
        # Never remove a notice if its verified representative is absent/expired.
        absent = shortlist(feed, date(2026, 11, 18),
                           verified_duplicate_representatives={'a2': 'a99'})
        self.assertEqual(absent['regular_review_candidate_rows'], 4)
        # A title-only coincidence is not a duplicate; only explicit proof
        # supplied by the identity-bound resolver may remove it.
        self.assertIn('a4', [r['id'] for r in after['regular_review_candidates']])


    def test_date_only_start_on_today_is_not_certified_as_current_regular_opening(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 11, 18, 3, 19, tzinfo=ZoneInfo('Asia/Seoul'))
        post = dict(row('a307067', due='2026-12-01', emp=['정규직'], n='6'),
                    alio=True, org='신용보증재단중앙회', title='정규직 신입')
        proof = {'a307067': dict(organization=post['org'], title=post['title'],
                                 source_end_date='2026-12-01',
                                 application_start='2026-11-18',
                                 application_end_date='2026-12-01')}
        feed = {'posts': [post]}
        before = __import__('copy').deepcopy(feed)
        report = shortlist(feed, date(2026, 11, 18), verified_windows=proof,
                           as_of_instant=now)
        # A public listing can remain a candidate, but same-day unknown
        # opening hour must not be certified as part of the current regular-20.
        self.assertEqual([x['id'] for x in report['top']], ['a307067'])
        self.assertEqual(report['regular_review_candidate_rows'], 0)
        self.assertEqual(report['regular_start_day_clock_unconfirmed_hold_ids'], ['a307067'])
        self.assertTrue(report['top'][0]['official_start_day_clock_unconfirmed'])
        tomorrow = shortlist(feed, date(2026, 11, 19), verified_windows=proof,
                             as_of_instant=datetime(2026, 11, 19, 0, 1,
                                                    tzinfo=ZoneInfo('Asia/Seoul')))
        self.assertEqual(tomorrow['regular_review_candidate_rows'], 1)
        self.assertEqual(tomorrow['regular_start_day_clock_unconfirmed_hold_ids'], [])
        historical = shortlist(feed, date(2026, 11, 18), verified_windows=proof)
        self.assertEqual(historical['regular_review_candidate_rows'], 1)
        changed = shortlist({'posts': [dict(post, title='변경된 공고')]},
                            date(2026, 11, 18), verified_windows=proof,
                            as_of_instant=now)
        self.assertEqual(changed['regular_review_candidate_rows'], 1)
        self.assertEqual(feed, before)

    def test_official_date_only_end_excludes_after_end_not_on_end_day(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        kst = ZoneInfo('Asia/Seoul')
        post = dict(row('a1', due='2026-12-01', emp=['정규직'], n='2'),
                    alio=True, org='기관A', title='정규직 경력')
        proof = {'a1': dict(organization=post['org'], title=post['title'],
                            source_end_date='2026-12-01',
                            application_start='2026-11-01',
                            application_end_date='2026-11-17')}
        last_day = shortlist({'posts':[post]}, date(2026, 11, 17),
                             verified_windows=proof,
                             as_of_instant=datetime(2026, 11, 17, 23, 59, tzinfo=kst))
        self.assertEqual([x['id'] for x in last_day['top']], ['a1'])
        next_day = shortlist({'posts':[post]}, date(2026, 11, 18),
                             verified_windows=proof,
                             as_of_instant=datetime(2026, 11, 18, 0, 1, tzinfo=kst))
        self.assertEqual(next_day['excluded']['official_reception_closed_by_date'], 1)
        self.assertEqual(next_day['regular_review_candidate_rows'], 0)
        # Unchanged but outdated confirmation must not suppress a reissued notice.
        revised = shortlist({'posts':[dict(post, due='2026-12-02')]},
                            date(2026, 11, 18), verified_windows=proof)
        self.assertEqual(len(revised['top']), 1)
        # An inconsistent official window is not sufficient evidence to exclude.
        bad = {'a1': {**proof['a1'], 'application_start': '2026-11-25'}}
        self.assertEqual(len(shortlist({'posts':[post]}, date(2026, 11, 18),
                                       verified_windows=bad)['top']), 1)

    def test_duplicate_guard_never_hides_regular_behind_ineligible_representative(self):
        # Resolver's proof says the notice originals match, but feed employment
        # classification or cautious title review can still differ. Preserve
        # at least one REGULAR review candidate rather than silently lose both.
        feed = {'posts': [
            dict(row('a20', emp=['정규직', '인턴'], n='12'), title='통합 채용'),
            dict(row('a21', emp=['정규직'], n='12'), title='통합 채용'),
            dict(row('a30', emp=['정규직'], n='9'), title='인턴 포함 정규채용'),
            dict(row('a31', emp=['정규직'], n='9'), title='일반 정규채용'),
            dict(row('a40', emp=['정규직'], n='3'), title='채용A'),
            dict(row('a41', emp=['정규직'], n='3'), title='채용A'),
        ]}
        report = shortlist(feed, date(2026, 11, 18),
                           verified_duplicate_representatives={
                               'a21': 'a20', 'a31': 'a30',
                               'a40': 'a41', 'a41': 'a40'})
        kept = {x['id'] for x in report['regular_review_candidates']}
        self.assertEqual(kept, {'a21', 'a31', 'a40', 'a41'})
        self.assertEqual(report['regular_review_verified_duplicate_exclusions'], [])
        self.assertIn('a30', report['regular_title_conflict_hold_ids'])
        self.assertEqual(report['eligible_rows'], 6)

    def test_duplicate_guard_preserves_candidate_when_representative_start_hour_unknown(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        rep = dict(row('a50', emp=['정규직'], n='5'), alio=True,
                   title='정규직 공채', org='기관Z')
        other = dict(row('a51', emp=['정규직'], n='5'),
                     title='정규직 공채', org='기관Z')
        proof = {'a50': {'organization': '기관Z', 'title': '정규직 공채',
                         'source_end_date': '2026-12-01',
                         'application_start': '2026-11-18'}}
        report = shortlist({'posts': [rep, other]}, date(2026, 11, 18),
                           verified_windows=proof,
                           verified_duplicate_representatives={'a51': 'a50'},
                           as_of_instant=datetime(2026, 11, 18, 4, 20,
                                                  tzinfo=ZoneInfo('Asia/Seoul')))
        self.assertEqual([x['id'] for x in report['regular_review_candidates']],
                         ['a51'])
        self.assertEqual(report['regular_start_day_clock_unconfirmed_hold_ids'],
                         ['a50'])
        self.assertEqual(report['regular_review_verified_duplicate_exclusions'], [])

    def test_conflicting_official_start_and_cutoff_never_hide_candidate(self):
        # Two internally contradictory official timestamps are not proof of closure.
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 11, 18, 18, 0, tzinfo=ZoneInfo('Asia/Seoul'))
        post = dict(row('a77', due='2026-12-01', emp=['정규직'], n='7'),
                    alio=True, title='정규 공채', org='기관Z')
        base = dict(organization='기관Z', title='정규 공채',
                    source_end_date='2026-12-01')
        conflicts = [
            dict(application_start='2026-11-19',
                 application_cutoff='2026-11-17T17:00:00+09:00'),
            dict(application_start='2026-11-18T18:00:00+09:00',
                 application_cutoff='2026-11-18T17:00:00+09:00'),
            dict(application_start='2026-11-01',
                 application_end_date='2026-11-19',
                 application_cutoff='2026-11-17T17:00:00+09:00'),
        ]
        for conflict in conflicts:
            with self.subTest(conflict=conflict):
                result = shortlist({'posts':[post]}, now.date(),
                                   verified_windows={'a77':{**base, **conflict}},
                                   as_of_instant=now)
                self.assertEqual([p['id'] for p in result['top']], ['a77'])
                self.assertEqual(result['regular_review_candidate_rows'], 1)
                self.assertFalse(result['excluded'])

    def test_invalid_official_kst_clock_is_not_used_or_parsed_as_proof(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 11, 18, 18, 0, tzinfo=ZoneInfo('Asia/Seoul'))
        post = dict(row('a77', due='2026-12-01', emp=['정규직']),
                    alio=True, title='정규 공채', org='기관Z')
        proof = {'a77': dict(organization='기관Z', title='정규 공채',
                             source_end_date='2026-12-01',
                             application_start='2026-11-18T99:00:00+09:00',
                             application_cutoff='2026-11-17T99:00:00+09:00')}
        result = shortlist({'posts':[post]}, now.date(),
                           verified_windows=proof, as_of_instant=now)
        self.assertEqual([p['id'] for p in result['top']], ['a77'])

    def test_no_fake_popularity_or_count(self):
        self.assertIsNone(seat_count('10명'))
        self.assertIsNone(seat_count('-1'))
        result=shortlist({'posts':[row('a1',n='10명')]},date(2026,11,9))
        self.assertTrue(any('Not a search-volume' in x for x in result['limitations']))
        self.assertIsNone(result['top'][0]['reported_seats'])

if __name__ == '__main__': unittest.main()
