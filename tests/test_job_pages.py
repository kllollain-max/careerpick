"""Regression tests for CareerPick generated ALIO job pages.

Run: python -m unittest discover -s tests -p 'test_job_pages.py'
"""
import unittest
import copy
import json
import re
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path

from scripts.build_job_pages import render


class JobPageTests(unittest.TestCase):
    def test_protected_notice_supplements_keep_existing_guidance_and_unique_anchors(self):
        from scripts.build_job_pages import VERIFIED_DUTIES
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        for pid in ['a306750', 'a306355', 'a306436']:
            post = posts[pid]; original = copy.deepcopy(post); html = render(post, {})
            self.assertEqual(html.count('id="verified-notice"'), 1)
            self.assertEqual(html.count('id="verified-notice-supplement"'), 1)
            self.assertIn('공고문 확인일: 2026-11-17', html)
            self.assertIn(VERIFIED_DUTIES[pid]['notice_source_url'], html)
            self.assertIn('원본 확인일: 2026-11-16', html)
            self.assertEqual(post, original)
        korail = render(posts['a306750'], {})
        self.assertIn('공무직(무기계약직) 6명과 계약직(기간제) 717명', korail)
        self.assertIn('구내운전직 280명·전호연료직 427명', korail)
        self.assertIn('2026-11-13 ~ 2026-11-19 10:00 (KST)', korail)
        self.assertIn('컨테이너크레인운전기능사와 지게차운전기능사', korail)

    def test_postal_daily_pool_does_not_invent_a_final_clock_or_live_vacancies(self):
        post = next(p for p in json.loads(Path('alio.json').read_text())['posts'] if p['id']=='a306436')
        html = render(post, {})
        self.assertIn('안양물류사업소 60명', html)
        self.assertIn('부평물류사업소 55명', html)
        self.assertIn('일 단위로 모집·근무', html)
        self.assertIn('현재 모두 공석', html)
        self.assertIn('기관 이메일이 표에 있다는 이유만으로 이메일 제출이 허용된다고 추정하지', html)
        self.assertNotIn('2026-11-30 23:59', html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        self.assertNotIn('application/ld+json', html)

    def test_expired_ibk_supplement_retains_history_and_correct_field_counts(self):
        post = next(p for p in json.loads(Path('alio.json').read_text())['posts'] if p['id']=='a306355')
        html = render(post, {})
        self.assertIn('접수 종료 공고', html)
        self.assertIn('금융일반 340명과 디지털·IT 50명', html)
        self.assertIn('서울·수도권 250명', html)
        self.assertIn('충청·강원권 20명', html)
        self.assertIn('AI역량검사 미응시자는 서류심사 불합격', html)
        self.assertNotIn('application/ld+json', html)

    def test_new_official_windows_preserve_publication_and_source_data(self):
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        for pid, start, end in [('a307067', '2026-11-18', '2026-12-01 15:00'),
                                ('a306816', '2026-11-18 10:00', '2026-11-25 18:00'),
                                ('a307024', '2026-11-23 10:00', '2026-11-30 10:00')]:
            p = posts[pid]; original = copy.deepcopy(p)
            html = render(p, {'pbancBgngYmd': p['pub'][:10]})
            self.assertIn(start + ' ~ ' + end + ' (KST)', html)
            self.assertIn('ALIO 게시 시작일', html)
            self.assertIn('원본 확인일: 2026-11-16', html)
            self.assertEqual(p, original)
        self.assertIn('경영·경제 4명, AI 2명', render(posts['a307067'], {}))
        self.assertIn('무기계약 14명과 기간제 28명', render(posts['a306816'], {}))
        self.assertIn('실무직 2명·공무직 21명', render(posts['a307024'], {}))

    def test_application_start_metadata_requires_valid_order_and_exact_source(self):
        from scripts.build_public_site import homepage_cutoff_metadata
        p = dict(id='a1', alio=True, org='기관', title='공고', due='2026-11-30')
        proof = dict(organization='기관', title='공고', application_start='2026-11-23T10:00:00+09:00')
        clocks = {'a1': '2026-11-30T10:00:00+09:00'}
        def metadata(): return homepage_cutoff_metadata([p], clocks, {'a1': proof})
        self.assertEqual(metadata()['a1']['start'], proof['application_start'])
        for value in ['2026-11-31', '2026-12-01', 'invalid', 42]:
            proof['application_start'] = value
            self.assertNotIn('start', metadata()['a1'])
        proof['application_start'] = '2026-11-23'; proof['title'] = '다른 공고'
        self.assertEqual(metadata(), {})

    def test_static_open_list_waits_for_official_start_and_preserves_source(self):
        from scripts.build_public_site import static_recruitment_posts
        posts = [dict(id='a1', pub='2026-11-16'), dict(id='other')]
        original = copy.deepcopy(posts)
        metadata = {'a1': dict(start='2026-11-18T10:00:00+09:00', cutoff='2026-11-25T18:00:00+09:00')}
        for stamp, expected in [('2026-11-18T00:59:59+00:00', ['other']),
                                ('2026-11-18T01:00:00+00:00', ['a1', 'other']),
                                ('2026-11-25T09:00:00+00:00', ['other'])]:
            result = static_recruitment_posts(posts, metadata, datetime.fromisoformat(stamp))
            self.assertEqual([p['id'] for p in result], expected)
        self.assertEqual(posts, original)

    def test_sector_notices_keep_field_counts_and_unknown_clock(self):
        from scripts.build_job_pages import VERIFIED_DUTIES
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        for pid, text in [('a306774', '106명'), ('a307046', '96명'),
                          ('a307061', '상담 51명과 미화 4명')]:
            html = render(posts[pid], {})
            self.assertIn('id="verified-notice"', html)
            self.assertIn(text, html)
            self.assertIn(VERIFIED_DUTIES[pid]['notice_source_url'], html)
        self.assertIn('2026-11-17 13:00 (KST)', render(posts['a306774'], {}))
        self.assertIn('2026-11-30 18:00 (KST)', render(posts['a307061'], {}))
        unknown = render(posts['a307046'], {})
        self.assertIn('마감시각은 공식 공고 확인 필요', unknown)
        self.assertNotIn('2026-11-30 23:59', unknown)

    def test_structured_notice_is_escaped_and_identity_bound(self):
        from scripts.build_job_pages import VERIFIED_DUTIES
        evidence = copy.deepcopy(VERIFIED_DUTIES['a307061'])
        evidence['notice_sections'] = [dict(heading='<script>bad</script>',
                                               paragraphs=['<img src=x onerror=bad>', 123]), None]
        post = dict(self.post, id='a307061', org=evidence['organization'], title=evidence['title'])
        with patch.dict(VERIFIED_DUTIES, {'a307061': evidence}):
            html = render(post, {})
            self.assertIn('&lt;script&gt;bad&lt;/script&gt;', html)
            self.assertNotIn('<img src=x onerror=bad>', html)
            self.assertNotIn('id="verified-notice"', render(dict(post, title='다른 공고'), {}))
            evidence['notice_source_url'] = 'javascript:alert(1)'
            self.assertNotIn('id="verified-notice"', render(post, {}))

    def test_homepage_cutoff_bundle_matches_reviewed_source_identity(self):
        from scripts.build_public_site import homepage_cutoff_metadata
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_DUTIES
        root = Path(__file__).resolve().parents[1]
        posts = json.loads((root / 'alio.json').read_text())['posts']
        original = copy.deepcopy(posts)
        result = homepage_cutoff_metadata(posts, CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_DUTIES)
        self.assertEqual(set(result), set(CONFIRMED_APPLICATION_CUTOFFS))
        self.assertEqual(result['a306355']['cutoff'], '2026-11-16T10:00:00+09:00')
        self.assertEqual(result['a307034']['cutoff'], '2026-11-20T16:00:00+09:00')
        self.assertEqual(posts, original)

    def test_homepage_cutoff_bundle_rejects_stale_or_unreviewed_identity(self):
        from scripts.build_public_site import homepage_cutoff_metadata
        post = dict(id='a1', alio=True, org='기관', title='공고', due='2026-11-20')
        proofs = {'a1': dict(organization='기관', title='공고')}
        clocks = {'a1': '2026-11-20T16:00:00+09:00'}
        self.assertIn('a1', homepage_cutoff_metadata([post], clocks, proofs))
        for change in ({'org': '다른 기관'}, {'title': '정정 공고'}, {'due': '2026-11-21'}, {'alio': False}):
            self.assertEqual(homepage_cutoff_metadata([dict(post, **change)], clocks, proofs), {})
        self.assertEqual(homepage_cutoff_metadata([post], clocks, {}), {})
        self.assertEqual(homepage_cutoff_metadata([post], {'a1': '2026-11-20'}, proofs), {})

    def test_yangju_notice_reconciles_attachment_without_overriding_feed(self):
        from scripts.build_job_pages import VERIFIED_DUTIES
        evidence = VERIFIED_DUTIES['a307034']
        post = dict(self.post, id='a307034', org=evidence['organization'],
                    title=evidence['title'], due='2026-11-20T23:59:00+09:00',
                    dueHasTime=False)
        original = copy.deepcopy(post)
        html = render(post, {})
        self.assertIn('2026-11-20 16:00 (KST)', html)
        self.assertNotIn('2026-11-20 23:59', html)
        self.assertNotIn('application/ld+json', html)
        self.assertIn('모집 3명 이하의 보훈 가점 미적용 원칙', html)
        self.assertIn('면접전형 가점으로 설명합니다', html)
        self.assertIn('우대 증빙 제출 시점도 ALIO 요약과 첨부', html)
        self.assertIn('근무 장소와 면접 장소가 다릅니다', html)
        self.assertIn('fileNo=3087622', html)
        self.assertEqual(post, original)
        for changed in ({'org': '다른 기관'}, {'title': '다른 공고'}, {'id': 'a307035'}):
            self.assertNotIn('id="verified-notice"', render(dict(post, **changed), {}))

    def test_yangju_archives_at_verified_16h_cutoff(self):
        post = dict(self.post, id='a307034', due='2026-11-20T23:59:00+09:00',
                    dueHasTime=False)
        with patch('scripts.build_job_pages.datetime') as clock:
            clock.fromisoformat.side_effect = datetime.fromisoformat
            clock.now.return_value = datetime(2026, 11, 20, 7, 0, 1, tzinfo=timezone.utc)
            html = render(post, {})
        self.assertIn('공식 확인된 원서접수 마감시각이 지난 보관 공고', html)
        self.assertIn('noindex,follow', html)
        self.assertNotIn('application/ld+json', html)

    def test_verified_pdf_summary_is_bound_to_notice_identity(self):
        from scripts.build_job_pages import VERIFIED_DUTIES
        for identity, evidence in VERIFIED_DUTIES.items():
            post = dict(self.post, id=identity, org=evidence['organization'], title=evidence['title'])
            html = render(post, {})
            self.assertIn(evidence['summary'], html)
            self.assertIn('공식 직무기술서에서 확인한 담당업무', html)
            self.assertIn(evidence['source_url'], html)
            self.assertIn(evidence['checked_on'], html)
            unrelated = render(dict(post, title='다른 모집분야'), {})
            self.assertNotIn(evidence['summary'], unrelated)
            wrong_org = render(dict(post, org='다른 기관'), {})
            self.assertNotIn(evidence['summary'], wrong_org)

    def test_verified_application_cutoff_expires_before_publication_end(self):
        post = {'id': 'a306355', 'alio': True, 'due': '2026-11-16T23:59:00+09:00'}
        with patch('scripts.build_job_pages.datetime') as clock:
            clock.fromisoformat.side_effect = datetime.fromisoformat
            clock.now.return_value = datetime(2026, 11, 16, 1, 0, 1, tzinfo=timezone.utc)
            html = render(post, {})
        self.assertIn('공식 확인된 원서접수 마감시각이 지난 보관 공고', html)
        self.assertIn('noindex,follow', html)
        self.assertNotIn('application/ld+json', html)
        self.assertEqual(post['due'], '2026-11-16T23:59:00+09:00')

    def test_verified_application_cutoff_remains_open_before_cutoff(self):
        post = {'id': 'a306355', 'alio': True, 'due': '2026-11-16T23:59:00+09:00'}
        with patch('scripts.build_job_pages.datetime') as clock:
            clock.fromisoformat.side_effect = datetime.fromisoformat
            clock.now.return_value = datetime(2026, 11, 16, 0, 59, 59, tzinfo=timezone.utc)
            html = render(post, {})
        self.assertNotIn('class="closed"', html)
        self.assertNotIn('noindex,follow', html)

    def setUp(self):
        self.post = {
            'id': 'a123456',
            'alio': True,
            'title': '채용 공고 테스트',
            'org': '테스트 기관',
            'due': '2026-12-31',
            # Synthetic fixture explicitly verifies its cutoff for JSON-LD tests.
            'dueHasTime': True,
            'pub': '2026-10-23',
            'emp': '정규직',
            'region': '강원',
            'desc': '실제 담당 업무와 필요한 역량을 안내하는 테스트용 채용공고입니다.',
            'src': 'https://example.org/jobs/123',
        }

    def test_unverified_cutoff_omits_jobposting_and_clock_time(self):
        post = dict(self.post, due='2099-12-31T23:59:00+09:00')
        post.pop('dueHasTime')
        html = render(post, {})
        self.assertNotIn('<script type="application/ld+json">', html)
        self.assertIn('<dt>ALIO 게시 종료일 · 접수마감 원문 확인</dt><dd>2099-12-31</dd>', html)
        self.assertNotIn('2099-12-31 23:59', html)

    def test_employer_confirmed_cutoff_only_on_matching_notice(self):
        confirmed = dict(self.post, id='a306750', due='2026-11-19T23:59:00+09:00')
        confirmed.pop('dueHasTime')
        html = render(confirmed, {})
        self.assertIn('<dt>기관 공식 확인 접수마감</dt><dd>2026-11-19 10:00 (KST)</dd>', html)
        self.assertIn('<dt>ALIO 게시 종료일 · 접수마감 원문 확인</dt><dd>2026-11-19</dd>', html)
        self.assertNotIn('<script type="application/ld+json">', html)
        other = render(dict(confirmed, id='a306436'), {})
        self.assertNotIn('기관 공식 확인 접수마감', other)
        self.assertNotIn('2026-11-19 10:00', other)

    def test_ibk_verified_cutoff_does_not_leak_to_other_notices(self):
        post = dict(self.post, id='a306355', due='2026-11-16T23:59:00+09:00')
        post.pop('dueHasTime')
        html = render(post, {})
        self.assertIn('<dt>기관 공식 확인 접수마감</dt><dd>2026-11-16 10:00 (KST)</dd>', html)
        self.assertIn('<dt>원서 접수기간</dt><dd>접수 시작일 및 변경 여부는 공식 공고에서 확인</dd>', html)
        self.assertNotIn('시작일·마감일·마감시각은 공식 첨부 공고에서 확인', html)
        self.assertIn('<dt>ALIO 게시 종료일 · 접수마감 원문 확인</dt><dd>2026-11-16</dd>', html)
        self.assertNotIn('2026-11-16 23:59', html)
        self.assertNotIn('<script type="application/ld+json">', html)
        other = render(dict(post, id='a306436'), {})
        self.assertNotIn('기관 공식 확인 접수마감', other)

    def test_postal_notice_verified_guidance_only_on_matching_notice(self):
        postal = dict(self.post, id='a306436', due='2026-11-30T23:59:00+09:00')
        postal.pop('dueHasTime')
        html = render(postal, {})
        self.assertIn('안양·부평 우편물구분 채용 확인사항', html)
        self.assertIn('적격자가 있으면 즉시 채용될 수 있습니다', html)
        self.assertIn('세부 담당업무는 공식 직무기술서 HWP 본문을 확인해야 합니다', html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        self.assertNotIn('2026-11-30 23:59', html)
        other = render(dict(postal, id='a306355'), {})
        self.assertNotIn('안양·부평 우편물구분 채용 확인사항', other)

    def test_ibk_source_checked_selection_guide_is_scoped(self):
        ibk = dict(self.post, id='a306355', due='2026-11-16T23:59:00+09:00')
        ibk.pop('dueHasTime')
        html = render(ibk, {})
        self.assertIn('IBK 체험형 청년인턴 지원 전 핵심 확인', html)
        self.assertIn('AI역량검사 미응시자는 서류심사 불합격', html)
        self.assertIn('2026년 11월 16일 오전 10시', html)
        self.assertNotIn('분야별 구체적 담당업무는 직무기술서 PDF 본문 검증 전까지 추정하지 않습니다.', render(dict(ibk, id='a306750'), {}))
        self.assertNotIn('IBK 체험형 청년인턴 지원 전 핵심 확인', render(dict(ibk, id='a306436'), {}))

    def test_korail_eligibility_comparison_is_scoped_to_one_notice(self):
        korail = dict(self.post, id='a306750', due='2026-11-19T23:59:00+09:00')
        korail.pop('dueHasTime')
        html = render(korail, {})
        self.assertIn('코레일유통 물류사업 채용 분야별 지원자격', html)
        self.assertIn('컨테이너크레인운전기능사', html)
        self.assertIn('철도운영단 전호연료직', html)
        self.assertIn('직종별 연령 기준 날짜가 다릅니다', html)
        self.assertIn('2027년 1월 4일 기준입니다', html)
        self.assertIn('만 18세 이상~만 60세 이하', html)
        self.assertIn('만 18세 이상~만 70세 미만', html)
        self.assertIn('실제 담당업무를 설명하는 직무기술서가 아닙니다', html)
        self.assertNotIn('2026-11-19 23:59', html)
        self.assertNotIn('코레일유통 물류사업 채용 분야별 지원자격',
                         render(dict(korail, id='a306355'), {}))

    def test_full_detail_regions_reach_summary_checks_metadata_and_schema(self):
        post = dict(self.post, region='인천')
        detail = {'recrutPblntSn': '123456', 'workRgnNmLst': '인천,충남,전북'}
        before = copy.deepcopy((post, detail))
        html = render(post, detail)
        self.assertIn('<dt>근무지역</dt><dd>인천, 충남, 전북</dd>', html)
        self.assertIn('표시된 근무지역은 인천, 충남, 전북입니다', html)
        self.assertIn('근무지역 인천, 충남, 전북', html)
        schema = json.loads(re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        ).group(1))
        self.assertEqual(schema['jobLocation'], [
            {'@type': 'Place', 'address': {
                '@type': 'PostalAddress', 'addressCountry': 'KR', 'addressRegion': region
            }} for region in ['인천', '충남', '전북']
        ])
        self.assertIn('근무지역: 인천, 충남, 전북.', schema['description'])
        self.assertNotIn('전국', html)
        self.assertEqual((post, detail), before)

    def test_region_detail_fallback_identity_and_no_inferred_locations(self):
        for detail in ({}, {'workRgnNmLst': ''}, {'workRgnNmLst': '  '},
                       {'workRgnNmLst': ['서울']},
                       {'recrutPblntSn': '999999', 'workRgnNmLst': '서울'}):
            with self.subTest(detail=detail):
                self.assertIn('<dt>근무지역</dt><dd>강원</dd>', render(self.post, detail))
        html = render(dict(self.post, region=''), {})
        self.assertIn('<dt>근무지역</dt><dd>공고 확인</dd>', html)
        self.assertNotIn('"jobLocation"', html)
        self.assertIn('<dt>근무지역</dt><dd>충남, 전북</dd>', render(
            self.post, {'workRgnNmLst': '충남|전북'}))
        self.assertIn('<dt>근무지역</dt><dd>강원</dd>', render(
            dict(self.post, alio=False), {'workRgnNmLst': '서울'}))

    def schema_from(self, html):
        return json.loads(re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        ).group(1))

    def test_single_region_keeps_one_place_and_korean_country(self):
        schema = self.schema_from(render(self.post, {'workRgnNmLst': '강원'}))
        self.assertEqual(schema['jobLocation'], {
            '@type': 'Place', 'address': {
                '@type': 'PostalAddress', 'addressCountry': 'KR', 'addressRegion': '강원'
            }
        })

    def test_unknown_regions_never_create_a_place(self):
        for region in ('', None, [], ' , | '):
            with self.subTest(region=region):
                schema = self.schema_from(render(dict(self.post, region=region), {}))
                self.assertNotIn('jobLocation', schema)

    def test_mismatched_notice_cannot_mix_regions_in_schema(self):
        post = dict(self.post, region='인천')
        detail = {'recrutPblntSn': '999999', 'workRgnNmLst': '충남,전북',
                  'aplyQlfcCn': '다른 공고의 지원 자격',
                  'scrnprcdrMthdExpln': '다른 공고의 전형 절차'}
        before = copy.deepcopy((post, detail))
        html = render(post, detail)
        self.assertEqual(self.schema_from(html)['jobLocation']['address']['addressRegion'], '인천')
        self.assertIn('<dt>근무지역</dt><dd>인천</dd>', html)
        self.assertNotIn('충남', html)
        self.assertNotIn('전북', html)
        self.assertNotIn('다른 공고의 지원 자격', html)
        self.assertNotIn('다른 공고의 전형 절차', html)
        self.assertEqual((post, detail), before)

    def test_selected_static_regeneration_preserves_other_file_and_input(self):
        post = dict(self.post, id='a306304', region='인천')
        detail = {'recrutPblntSn': '306304', 'workRgnNmLst': '인천,충남,전북',
                  'aplyQlfcCn': '지원 자격 원문 보존'}
        before = copy.deepcopy((post, detail))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = root / 'a123456.html'
            other.write_bytes(b'previous unrelated page')
            target = root / 'a306304.html'
            target.write_text(render(post, detail), encoding='utf-8')
            html = target.read_text(encoding='utf-8')
            schema = self.schema_from(html)
            self.assertEqual([p['address']['addressRegion'] for p in schema['jobLocation']],
                             ['인천', '충남', '전북'])
            self.assertIn('지원 자격 원문 보존', html)
            self.assertIn('href="https://example.org/jobs/123"', html)
            self.assertIn('rel="canonical" href="https://kllollain-max.github.io/careerpick/jobs/a306304.html"', html)
            self.assertEqual(schema['url'], 'https://kllollain-max.github.io/careerpick/jobs/a306304.html')
            self.assertEqual(other.read_bytes(), b'previous unrelated page')
            self.assertEqual((post, detail), before)

    def test_official_duties_checklist_does_not_invent_job_description(self):
        html = render(self.post, {'aplyQlfcCn': '자격요건 원문'})
        self.assertIn('실제 담당업무는 어디서 확인하나요?', html)
        self.assertIn('직무기술서 또는 모집분야별 설명', html)
        self.assertIn('공식 문의처에 확인하세요', html)
        self.assertIn('공고별 업무를 추정한 설명이 아니라', html)

    def test_correction_notice_guide_is_linked(self):
        html = render(self.post, {})
        self.assertIn('/guides/recruitment-corrections-guide.html', html)
        self.assertIn('정정공고·마감 변경 대응법', html)

    def test_mobile_layout_and_keyboard_navigation(self):
        html = render(self.post, {})
        self.assertIn('class="skip-link" href="#job-summary"', html)
        self.assertIn('<h2 id="job-summary">모집 요약</h2>', html)
        self.assertIn('a:focus-visible', html)
        self.assertIn('.apply{display:block;text-align:center', html)
        self.assertIn('box-sizing:border-box', html)

    def test_detail_content_and_official_link(self):
        html = render(self.post, {
            'aplyQlfcCn': '관련 자격증 필수',
            'scrnprcdrMthdExpln': '서류 심사 후 면접',
            'prefCn': '국가유공자 우대',
            'prefCondCn': '관련 경력 우대',
        })
        self.assertIn('지원 전 핵심 확인사항', html)
        self.assertIn('관련 자격증 필수', html)
        self.assertIn('서류 심사 후 면접', html)
        self.assertIn('<h2>전형 절차</h2>', html)
        self.assertIn('국가유공자 우대', html)
        self.assertIn('관련 경력 우대', html)
        self.assertIn('https://example.org/jobs/123', html)
        self.assertIn('관련 취업 준비 자료', html)
        self.assertNotIn('<h2>지원 전 체크리스트</h2>', html)
        self.assertNotIn('<h2>공고 핵심정보</h2>', html)

    def test_official_link_explains_application_site_difference(self):
        html = render(self.post, {})
        self.assertIn('공식 원문 및 지원 방법 확인', html)
        self.assertIn('별도의 채용 접수 사이트로 이동해야 할 수 있습니다', html)
        self.assertIn('공식 채용공고 열기', html)
        self.assertIn('rel="noopener noreferrer"', html)

    def test_missing_official_link_has_no_false_apply_button(self):
        post = dict(self.post)
        post.pop('src', None)
        post.pop('url', None)
        html = render(post, {})
        self.assertIn('공식 링크를 확인할 수 없습니다', html)
        self.assertNotIn('공식 채용공고 열기', html)

    def test_repeated_alio_title_not_rendered_as_detail(self):
        html = render(self.post, {
            'recrutPblntTtl': '채용 공고 테스트',
            'recrutSeNm': '신입',
            'aplyQlfcCn': '자격증 필수',
        })
        self.assertEqual(html.count('<h1>채용 공고 테스트</h1>'), 1)
        self.assertNotIn('<h2>채용공고 제목</h2>', html)
        self.assertIn('<h2>채용 구분</h2>', html)
        self.assertIn('<h2>지원 자격</h2>', html)

    def test_multiline_details_preserved(self):
        html = render(self.post, {
            'aplyQlfcCn': '1. 필수 조건\\n2. 우대 조건',
        })
        self.assertIn('class="detail-text"', html)
        self.assertIn('1. 필수 조건\\n2. 우대 조건', html)
        self.assertIn('white-space:pre-wrap', html)

    def test_long_official_detail_is_not_silently_cut_at_1500(self):
        detail = '지원 자격 안내 ' * 150
        html = render(self.post, {'aplyQlfcCn': detail})
        self.assertIn(detail, html)
        self.assertNotIn('이 항목은 원문이 길어 일부만 표시됩니다', html)

    def test_very_long_official_detail_has_explicit_truncation_notice(self):
        detail = '자격 조건 ' * 1200
        html = render(self.post, {'aplyQlfcCn': detail})
        self.assertIn('이 항목은 원문이 길어 일부만 표시됩니다', html)
        self.assertIn('전체 내용은 반드시 공식 채용공고에서 확인하세요', html)

    def test_disqualification_field_is_rendered(self):
        html = render(self.post, {'disqlfcRsn': '결격사유 원문 확인'})
        self.assertIn('<h2>결격사유</h2>', html)
        self.assertIn('결격사유 원문 확인', html)

    def test_disqualification_field_is_not_fabricated(self):
        html = render(self.post, {})
        self.assertNotIn('<h2>결격사유</h2>', html)

    def test_missing_details_are_not_invented(self):
        html = render(self.post, {})
        self.assertIn('상세 자격·전형 데이터가 제공되지 않았습니다', html)
        self.assertNotIn('관련 자격증 필수', html)

    def test_ncs_classification_alone_does_not_imply_written_exam(self):
        post = dict(self.post, title='공공기관 NCS 직무 채용', desc='NCS 경영·사무 직무 분류')
        html = render(post, {'scrnprcdrMthdExpln': '서류전형 후 면접'})
        self.assertNotIn('NCS 4주 학습 계획', html)

    def test_ncs_written_exam_in_selection_process_shows_guide(self):
        html = render(self.post, {'scrnprcdrMthdExpln': '서류심사 → NCS 직업기초능력 필기시험 → 면접'})
        self.assertIn('NCS 4주 학습 계획', html)

    def test_generic_written_exam_does_not_imply_ncs(self):
        html = render(self.post, {'scrnprcdrMthdExpln': '서류심사 → 전공 필기시험 → 면접'})
        self.assertNotIn('NCS 4주 학습 계획', html)

    def test_ncs_assessment_in_document_screening_not_written_exam(self):
        html = render(self.post, {'scrnprcdrMthdExpln': '1. 서류전형\\n- 평가: 직업기초능력(40%)\\n2. 면접전형\\n- 평가: 직업기초역량(40%)'})
        self.assertNotIn('NCS 4주 학습 계획', html)

    def test_ncs_exam_on_next_line_is_detected(self):
        html = render(self.post, {'scrnprcdrMthdExpln': '2차 : 필기전형\\n- 직무공통능력검사(NCS - 의사소통능력, 문제해결능력)\\n3차 : 면접전형'})
        self.assertIn('NCS 4주 학습 계획', html)

    def test_ncs_assessment_in_written_exam_section(self):
        html = render(self.post, {'scrnprcdrMthdExpln': '다. 필기전형\\n - NCS직업 기초능력\\n - 인성검사\\n라. 면접전형'})
        self.assertIn('NCS 4주 학습 계획', html)

    def test_long_ncs_classification_is_not_presented_as_job_duties(self):
        post = dict(
            self.post,
            desc='경영·회계·사무 · 총무·인사 · 재무·회계 · 사무행정 · '
                 '경영기획 · 일반사무 · 기타 공공기관 직무 분류',
        )
        html = render(post, {'aplyQlfcCn': '지원 가능'})
        self.assertIn('<h2>직무 분류</h2>', html)
        self.assertIn('직무 분류는 실제 담당업무 설명이 아닙니다', html)
        self.assertNotIn('<h2>공고 세부 요약</h2>', html)
        self.assertIn('공식 원문에서 추가 확인할 항목: 상세 직무 설명', html)

    def test_html_escaping(self):
        post = dict(self.post, title='<script>alert(1)</script>')
        html = render(post, {})
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<h1><script>', html)


if __name__ == '__main__':
    unittest.main()



class OriginalNoticeComparisonTests(unittest.TestCase):
    def setUp(self):
        from scripts.notice_review import resolve
        self.posts = json.loads(Path('alio.json').read_text())['posts']
        self.details = json.loads(Path('alio-detail.json').read_text())
        self.rules = json.loads(Path('scripts/verified_notice_reviews.json').read_text())
        self.reviews = resolve(self.posts, self.details, self.rules)

    def test_only_original_confirmed_pair_canonicalizes_and_keeps_bookmark_content(self):
        self.assertEqual(len(self.reviews), 8)
        for old, new in [('a305959','a306724'), ('a306564','a306800')]:
            post = next(p for p in self.posts if p['id'] == old)
            before = copy.deepcopy(post)
            html = render(post, self.details[old], notice_review=self.reviews[old])
            self.assertIn(f'rel="canonical" href="https://kllollain-max.github.io/careerpick/jobs/{new}.html"', html)
            self.assertIn(post['title'], html)
            self.assertIn('동일 채용의 대표 공고 보기', html)
            self.assertNotIn('application/ld+json', html)
            self.assertEqual(post, before)

    def test_similar_titles_with_different_worksite_or_specialty_keep_self_canonical(self):
        for pid, text in [('a298710','창원 1명'), ('a299406','진주 1명'), ('a295395','소화기내과 우대'), ('a296837','신경과')]:
            post = next(p for p in self.posts if p['id'] == pid)
            html = render(post, self.details[pid], notice_review=self.reviews[pid])
            self.assertIn(f'rel="canonical" href="https://kllollain-max.github.io/careerpick/jobs/{pid}.html"', html)
            self.assertIn(text, html)
            self.assertNotIn('동일 채용의 대표 공고 보기', html)

    def test_changed_peer_identity_or_terms_disable_entire_pair(self):
        from scripts.notice_review import resolve
        for field in ['org','title','n','due','pub','src','region']:
            posts = copy.deepcopy(self.posts)
            next(p for p in posts if p['id']=='a306724')[field] = 'changed'
            resolved = resolve(posts, self.details, self.rules)
            self.assertNotIn('a305959', resolved)
            self.assertNotIn('a306724', resolved)
        details = copy.deepcopy(self.details)
        details['a306724']['aplyQlfcCn'] = 'changed qualification'
        self.assertNotIn('a305959', resolve(self.posts, details, self.rules))
        self.assertNotIn('a305959', resolve([p for p in self.posts if p['id']!='a306724'], self.details, self.rules))

    def test_different_original_bytes_or_external_representative_never_merge(self):
        from scripts.notice_review import resolve
        rules = copy.deepcopy(self.rules)
        rules[0]['members'][0]['sources'][0]['sha256'] = '0'*64
        self.assertNotIn('a305959', resolve(self.posts, self.details, rules))
        rules = copy.deepcopy(self.rules)
        rules[0]['representative_id'] = 'https://example.com'
        self.assertNotIn('a305959', resolve(self.posts, self.details, rules))

    def test_stale_render_review_cannot_override_other_notice(self):
        post = next(p for p in self.posts if p['id']=='a306750')
        html = render(post, self.details[post['id']], notice_review=self.reviews['a305959'])
        self.assertIn('/jobs/a306750.html', html)
        self.assertNotIn('id="notice-review"', html)
