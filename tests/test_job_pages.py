"""Regression tests for CareerPick generated ALIO job pages.

Run: python -m unittest discover -s tests -p 'test_job_pages.py'
"""
import unittest
import copy
import json
import re
import tempfile
from html import escape as html_escape
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path

from scripts.build_job_pages import render


class JobPageTests(unittest.TestCase):

    def test_until_filled_pharmacist_source_guards_bind_headcount_and_employment(self):
        """Legacy until-filled 20/19 seats cannot keep stale editorial facts after ALIO changes."""
        from scripts.build_job_pages import VERIFIED_DUTIES
        from scripts.build_public_site import homepage_cutoff_metadata

        posts = {p['id']: p for p in json.loads(
            Path('alio.json').read_text(encoding='utf-8'))['posts']}
        for pid, seats in (('a292472', '20'), ('a299412', '19')):
            with self.subTest(pid=pid):
                post = posts[pid]
                original = copy.deepcopy(post)
                proof = VERIFIED_DUTIES[pid]
                self.assertTrue(proof['strict_source_identity'])
                self.assertTrue(proof['application_status_unconfirmed'])
                self.assertEqual(proof['expected_source_seats'], seats)
                self.assertEqual(proof['source_employment'], ['정규직'])
                self.assertEqual(post['n'], seats)
                self.assertEqual(post['emp'], ['정규직'])
                self.assertIn(proof['summary'], render(post, {}))
                self.assertIn(pid, homepage_cutoff_metadata([post], {}, {pid: proof}))
                for changed in (
                    {'n': '1'}, {'emp': ['계약직']},
                    {'title': post['title'] + ' 정정'}, {'org': '다른 기관'},
                    {'due': '2027-01-01T23:59:00+09:00'}, {'alio': False},
                ):
                    altered = {**post, **changed}
                    self.assertNotIn(proof['summary'], render(altered, {}))
                    self.assertNotIn(proof['applicant_check'], render(altered, {}))
                    self.assertNotIn(
                        pid, homepage_cutoff_metadata([altered], {}, {pid: proof}))
                self.assertEqual(post, original)

    def test_pnuh_thirty_three_role_split_and_original_1700_cutoff(self):
        """Official PDF/ZIP proves 30+2+1 and 17:00; all editorial facts are identity-bound."""
        from scripts.build_job_pages import (
            VERIFIED_DUTIES, VERIFIED_APPLICATION_NOTICES, CONFIRMED_APPLICATION_CUTOFFS,
        )
        posts = {p['id']: p for p in json.loads(
            Path('alio.json').read_text(encoding='utf-8'))['posts']}
        post = posts['a307225']
        original = copy.deepcopy(post)
        duty = VERIFIED_DUTIES['a307225']
        notice = VERIFIED_APPLICATION_NOTICES['a307225']
        self.assertEqual(
            (post['org'], post['title'], post['n'], post['emp'], post['due'][:10]),
            (duty['organization'], duty['title'], '33', ['정규직'], '2026-12-03'),
        )
        self.assertEqual(notice['hiring_breakdown'],
                         '진료지원간호사 30명 · 의료사회복지사 2명 · 산부인과 초음파실 방사선사 1명 = 정규직 총33명')
        self.assertEqual(duty['notice_source_sha256'],
                         'a45a7bebec1929e6f18315ee8ace0aa20b59ddf6af5cb40503d206f46faa3cd2')
        self.assertEqual(duty['source_sha256'],
                         '5919b21c2acdd40383a34da232ab3808cc6b0ca01e904a2cb5b26dce8fca10cf')
        self.assertEqual(CONFIRMED_APPLICATION_CUTOFFS['a307225'],
                         '2026-12-03T17:00:00+09:00')
        self.assertFalse(post['dueHasTime'])
        html = render(post, {})
        for phrase in (
            '진료지원간호사 30명', '의료사회복지사 2명', '산부인과', '방사선사 1명',
            '2026-12-03 17:00', '기관 공식 확인 접수마감', '심장초음파',
            '간호사면허', 'fileNo=3088502', 'fileNo=3088504',
        ):
            self.assertIn(phrase, html)
        self.assertNotIn('기관 공식 확인 접수마감: 2026-12-03 23:59', html)
        for changes in (
            {'n': '32'}, {'title': post['title'] + ' 변경'}, {'org': '다른 기관'},
            {'emp': ['계약직']}, {'due': '2026-12-04T23:59:00+09:00'},
            {'alio': False},
        ):
            changed_html = render({**post, **changes}, {})
            self.assertNotIn('진료지원간호사 30명', changed_html)
            self.assertNotIn('fileNo=3088504', changed_html)
            self.assertNotIn('기관 공식 확인 접수마감: 2026-12-03 17:00', changed_html)
        self.assertEqual(post, original)

    def test_new_changwon_pharmacist_five_overlapping_notice_warning_source_bound(self):
        """ALIO 5 planned seats cannot be summed with nine historic same-employer notices."""
        from scripts.build_job_pages import (
            VERIFIED_APPLICATION_NOTICES, VERIFIED_DUTIES, CONFIRMED_APPLICATION_CUTOFFS,
        )
        posts = json.loads(Path('alio.json').read_text(encoding='utf-8'))['posts']
        post = next(p for p in posts if p['id'] == 'a307251')
        original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a307251']
        self.assertEqual((post['org'], post['title'], post['n'], post['emp']),
                         (proof['organization'], proof['title'], '5', ['정규직']))
        self.assertEqual(post['due'][:10], proof['source_end_date'])
        self.assertFalse(post['dueHasTime'])
        overlap = [p for p in posts if
                   p['org'] == post['org'] and '약무직' in p['title'] and
                   p['id'] != 'a307251']
        known_prior = {'a294598', 'a294624', 'a297599', 'a298427',
                       'a303321', 'a305304', 'a292472', 'a299412', 'a306275'}
        self.assertTrue(known_prior.issubset({p['id'] for p in overlap}))
        self.assertNotIn('a307251', VERIFIED_DUTIES)
        self.assertNotIn('a307251', CONFIRMED_APPLICATION_CUTOFFS)
        self.assertTrue(proof['application_status_unconfirmed'])
        html = render(post, {})
        self.assertIn('<meta name="robots" content="noindex,follow">', html)
        for phrase in ('2027년 면허 취득예정자', '약무직 유사 공고',
                       '현재 남은 결원이 5명이라고 단정하지 마세요',
                       '실제 원서접수 마감시각', 'idx=307251'):
            self.assertIn(phrase, html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        self.assertNotIn('2026-12-31 23:59 (KST)', html)
        for changed in ({'n': '6'}, {'title': post['title'] + ' 정정'},
                        {'org': '변경 기관'}, {'due': '2027-01-01T23:59:00+09:00'},
                        {'emp': ['계약직']}, {'alio': False}):
            stale = render({**post, **changed}, {})
            self.assertNotIn('약무직 유사 공고', stale)
            self.assertNotIn('2027년 면허 취득예정자', stale)
            self.assertNotIn('<meta name="robots" content="noindex,follow">', stale)
        self.assertEqual(post, original)

    def test_knuh_pharmacist_eleven_conditional_vacancies_and_no_fake_cutoff(self):
        """Until-filled pharmacist notice is not 11 currently open independent seats."""
        from scripts.build_job_pages import (
            VERIFIED_APPLICATION_NOTICES, VERIFIED_DUTIES,
            CONFIRMED_APPLICATION_CUTOFFS,
        )
        posts = {p['id']: p for p in json.loads(
            Path('alio.json').read_text(encoding='utf-8'))['posts']}
        post = posts['a306182']
        original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306182']
        self.assertEqual((post['org'], post['title'], post['n'], post['emp']),
                         (proof['organization'], proof['title'], '11', ['정규직']))
        self.assertEqual(post['due'][:10], proof['source_end_date'])
        self.assertFalse(post['dueHasTime'])
        self.assertIn('a306182', VERIFIED_DUTIES)
        self.assertEqual(VERIFIED_DUTIES['a306182']['source_sha256'], 'd36d8a1995b99faf57a5238d1d19f1b4dc4958fd2f40f122e92e3c644881fb55')
        self.assertNotIn('a306182', CONFIRMED_APPLICATION_CUTOFFS)
        self.assertTrue(proof['application_status_unconfirmed'])
        html = render(post, {})
        self.assertIn('<meta name="robots" content="noindex,follow">', html)
        self.assertNotIn('type="application/ld+json"', html)
        from scripts.priority_candidate_audit import shortlist
        from datetime import date
        result = shortlist({'posts': [post]}, date(2026, 11, 19),
                           verified_windows={'a306182': proof})
        self.assertEqual(result['excluded']['official_current_status_unconfirmed'], 1)
        self.assertEqual(result['regular_review_candidates'], [])
        for phrase in ('약사 면허증', '11명은', '충원 시까지',
                       '2026-04-01', '2026-12-31',
                       '현재 접수 활성·잔여 인원 미확인',
                       '공식 충원조건부 원서접수 안내',
                       '개별 전형', '추가 공고와 인원을 자동 합산',
                       'b_num=7452'):
            self.assertIn(phrase, html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        self.assertNotIn('2026-12-31 23:59 (KST)', html)
        for changes in ({'n': '10'}, {'org': '정정된 기관'},
                        {'title': post['title'] + ' 변경'},
                        {'due': '2027-01-01T23:59:00+09:00'},
                        {'emp': ['비정규직']}, {'alio': False}):
            stale = render({**post, **changes}, {})
            self.assertNotIn('현재 접수 활성·잔여 인원 미확인', stale)
            self.assertNotIn('b_num=7452', stale)
            self.assertNotIn('예정인원 충원 후 접수자의 전형', stale)
            self.assertNotIn('<meta name="robots" content="noindex,follow">', stale)
        self.assertEqual(post, original)

    def test_cvhd_dental_resident_eleven_official_notice_only_and_exact_identity(self):
        """Official ALIO 5+3+3 dental resident notice; no unverified HWP duties or clock."""
        from scripts.build_job_pages import (
            VERIFIED_APPLICATION_NOTICES, VERIFIED_DUTIES,
            CONFIRMED_APPLICATION_CUTOFFS,
        )
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306992']
        original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306992']
        self.assertEqual((post['org'], post['title'], post['n'], post['emp']),
                         (proof['organization'], proof['title'], '11', ['정규직']))
        self.assertEqual(post['due'][:10], proof['source_end_date'])
        self.assertFalse(post['dueHasTime'])
        self.assertIn('a306992', VERIFIED_DUTIES)
        self.assertEqual(VERIFIED_DUTIES['a306992']['source_sha256'], '2974abde58a6d030771a23f6b05378a0c0a8d29b33a7134d43baf79515176fca')
        self.assertNotIn('a306992', CONFIRMED_APPLICATION_CUTOFFS)
        html = render(post, {})
        for phrase in ('보철과 5명', '치주과 3명', '보존과 3명',
                       '교육수련부 방문 제출', '중복 지원', '인턴 기수료자',
                       '2026-11-16 ~ 2026-11-20 (마감시각 공식 공고 확인 필요)',
                       '11월 29일 공동 필기시험', '공공의료 관련 업무',
                       'job.alio.go.kr/recruitview.do?idx=306992'):
            self.assertIn(phrase, html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        self.assertNotIn('2026-11-20 23:59 (KST)', html)
        for changes in ({'n': '12'}, {'title': post['title'] + ' 수정'},
                        {'org': '변경 기관'}, {'due': '2026-11-21T23:59:00+09:00'},
                        {'emp': ['계약직']}, {'alio': False}):
            stale = render({**post, **changes}, {})
            self.assertNotIn('보철과 5명', stale)
            self.assertNotIn('교육수련부 방문 제출', stale)
            self.assertNotIn('11월 29일 공동 필기시험', stale)
        self.assertEqual(post, original)

    def test_kipf_ten_public_ejm_utc_deadline_and_documents_are_source_bound(self):
        """Actual EJM accepts applications; UTC midnight is not synthetic KST 23:59."""
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES, VERIFIED_DUTIES, CONFIRMED_APPLICATION_CUTOFFS
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a305734']
        original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a305734']
        self.assertEqual((post['org'], post['title'], post['n'], post['emp']),
                         (proof['organization'], proof['title'], '10', ['정규직']))
        self.assertEqual(post['due'][:10], proof['source_end_date'])
        self.assertEqual(post['dueHasTime'], False)
        self.assertNotIn('a305734', CONFIRMED_APPLICATION_CUTOFFS)
        self.assertIn('a305734', VERIFIED_DUTIES)
        self.assertEqual(VERIFIED_DUTIES['a305734']['source_sha256'], '37dd16fa018543d5ca1cc108ed2c2757570bbb723fe2cd715e4c3d2320257654')
        html = render(post, {})
        for phrase in ('Research Fellow', '박사학위', '추천인 3명', 'Job market paper',
                       '2026-10-06 ~ 2026-11-30', 'midnight UTC',
                       '한국시간 종료시각 미확정', 'accepting applications',
                       'econjobmarket.org/positions/12745', 'fileNo=3079033'):
            self.assertIn(phrase, html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        self.assertNotIn('2026-11-30 23:59 (KST)', html)
        for changes in ({'n': '11'}, {'title': post['title']+' 정정'},
                        {'org': '다른 기관'}, {'due': '2026-12-01T23:59:00+09:00'},
                        {'emp': ['계약직']}, {'alio': False}):
            stale = render({**post, **changes}, {})
            self.assertNotIn('midnight UTC', stale)
            self.assertNotIn('추천인 3명', stale)
            self.assertNotIn('econjobmarket.org/positions/12745', stale)
        self.assertEqual(post, original)

    def test_snubh_cleaning_ten_original_duty_and_date_only_reception_guarded(self):
        """Exact official cleaning notice/duties; no invented cutoff time."""
        from scripts.build_job_pages import VERIFIED_DUTIES, CONFIRMED_APPLICATION_CUTOFFS
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306874']
        original = copy.deepcopy(post)
        proof = VERIFIED_DUTIES['a306874']
        self.assertEqual((post['org'], post['title'], post['n'], post['emp']),
                         (proof['organization'], proof['title'], '10', ['정규직']))
        self.assertEqual(post['due'][:10], proof['source_end_date'])
        self.assertNotIn('a306874', CONFIRMED_APPLICATION_CUTOFFS)
        html = render(post, {})
        for phrase in ('격리폐기물', '페이퍼타월', '정규직 미화 단일직무 10명',
                       '11월 11~20일', '수습기간', '마감시각 공식 공고 확인 필요',
                       'fileNo=3086117', 'fileNo=3086129'):
            self.assertIn(phrase, html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        for change in ({'n': '11'}, {'title': post['title'] + ' 정정'},
                       {'org': '다른 기관'}, {'due': '2026-11-21T23:59:00+09:00'},
                       {'emp': ['계약직']}, {'alio': False}):
            stale = render({**post, **change}, {})
            self.assertNotIn('격리폐기물', stale)
            self.assertNotIn('정규직 미화 단일직무 10명', stale)
            self.assertNotIn('fileNo=3086117', stale)
        self.assertEqual(post, original)

    def test_cnuh_three_official_17h_receipt_cutoffs_bound_to_exact_source(self):
        """Official PDF dates, not synthetic ALIO 23:59, govern all 3 notices."""
        from datetime import date
        from zoneinfo import ZoneInfo
        from scripts.build_job_pages import (
            VERIFIED_APPLICATION_NOTICES, CONFIRMED_APPLICATION_CUTOFFS,
        )
        from scripts.build_public_site import homepage_cutoff_metadata
        from scripts.priority_candidate_audit import shortlist

        cases = [('a306733', '21'), ('a306735', '49'), ('a306737', '29')]
        before = datetime(2026, 11, 19, 16, 59, tzinfo=ZoneInfo('Asia/Seoul'))
        closed = datetime(2026, 11, 19, 17, 0, tzinfo=ZoneInfo('Asia/Seoul'))
        for pid, seats in cases:
            proof = VERIFIED_APPLICATION_NOTICES[pid]
            post = {
                'id': pid, 'alio': True, 'org': proof['organization'],
                'title': proof['title'], 'n': seats, 'emp': ['정규직'],
                'due': '2026-11-19T23:59:00+09:00',
                'dueHasTime': False,
                'url': f'https://job.alio.go.kr/recruitview.do?idx={pid[1:]}',
            }
            original = copy.deepcopy(post)
            self.assertEqual(CONFIRMED_APPLICATION_CUTOFFS[pid],
                             '2026-11-19T17:00:00+09:00')
            self.assertEqual(proof['application_start'], '2026-11-05')
            self.assertEqual(proof['source_employment'], post['emp'])
            metadata = homepage_cutoff_metadata(
                [post], CONFIRMED_APPLICATION_CUTOFFS, {pid: proof})
            self.assertEqual(metadata[pid]['cutoff'],
                             '2026-11-19T17:00:00+09:00')
            html = render(post, {})
            self.assertIn('2026-11-19 17:00', html)
            self.assertIn('기관 공식 확인 접수마감', html)
            if pid == 'a306733':
                self.assertIn('환경사 13명', html)
                self.assertIn('보조원 6명', html)
            windows = {pid: {**proof,
                             'application_cutoff': CONFIRMED_APPLICATION_CUTOFFS[pid]}}
            fresh = shortlist({'posts': [post]}, date(2026, 11, 19),
                              as_of_instant=before, verified_windows=windows)
            self.assertEqual([p['id'] for p in fresh['top']], [pid])
            expired = shortlist({'posts': [post]}, date(2026, 11, 19),
                                as_of_instant=closed, verified_windows=windows)
            self.assertEqual(expired['top'], [])
            self.assertEqual(expired['excluded']['official_reception_closed'], 1)
            for changed in ({'title': '새 정정 공고'},
                            {'org': '다른 기관'}, {'n': '100'},
                            {'emp': ['계약직']},
                            {'due': '2026-11-20T23:59:00+09:00'},
                            {'alio': False}):
                revised = {**post, **changed}
                self.assertNotIn(pid, homepage_cutoff_metadata(
                    [revised], CONFIRMED_APPLICATION_CUTOFFS, {pid: proof}))
                stale_html = render(revised, {})
                self.assertNotIn('기관 공식 확인 접수마감', stale_html)
                self.assertNotIn('환경사 13명', stale_html)
            self.assertEqual(post, original)

    def test_pola_open_position_alio_employment_discrepancy_is_disclosed_only_when_source_matches(self):
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES, CONFIRMED_APPLICATION_CUTOFFS
        from scripts.priority_candidate_audit import shortlist
        from datetime import date

        feed = json.loads(Path('alio.json').read_text(encoding='utf-8'))['posts']
        by_id = {p['id']: p for p in feed}
        posts = []
        for pid, place in [('a307146', '인천국제물류사업소장'),
                           ('a307147', '안동사업소장')]:
            post = by_id[pid]
            original = copy.deepcopy(post)
            proof = VERIFIED_APPLICATION_NOTICES[pid]
            self.assertEqual(proof['organization'], post['org'])
            self.assertEqual(proof['title'], post['title'])
            self.assertEqual(proof['expected_source_seats'], '1')
            self.assertEqual(proof['source_employment'], ['정규직'])
            self.assertNotIn('confirmed_employment', proof)
            self.assertNotIn('application_start', proof)
            self.assertNotIn(pid, CONFIRMED_APPLICATION_CUTOFFS)
            html = render(post, {})
            self.assertIn(place, html)
            self.assertIn('전형단계별 채용정보는 개방형 계약직', html)
            self.assertIn('공식 첨부 HWP와 기관 지원창에서 확인 필요', html)
            self.assertNotIn('공식 공고문 고용형태', html)
            self.assertNotIn('기관 공식 확인 접수마감', html)
            for change in ({'n': '2'}, {'emp': ['무기계약직']},
                           {'title': post['title'] + ' 정정'}, {'org': '다른기관'},
                           {'due': '2026-12-02T23:59:00+09:00'}, {'alio': False}):
                stale = render({**post, **change}, {})
                self.assertNotIn('전형단계별 채용정보는 개방형 계약직', stale)
                self.assertNotIn('원서접수 개시·마감시각 및 정확한 고용계약 조건', stale)
            self.assertEqual(post, original)
            posts.append(post)
        # The editorial regular-only queue already holds '개방형직위'
        # title conflicts. The original source classification remains intact.
        report = shortlist({'posts': posts}, date(2026, 11, 19))
        self.assertEqual(report['regular_review_candidates'], [])
        self.assertEqual(set(report['regular_title_conflict_hold_ids']),
                         {'a307146', 'a307147'})
        self.assertEqual({p['id'] for p in report['top']},
                         {'a307146', 'a307147'})

    def test_pnuh_33_official_notice_summary_updated_after_original_pdf_review(self):
        """Former date-only HTML review is superseded by original PDF 17:00 evidence."""
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES, CONFIRMED_APPLICATION_CUTOFFS
        proof = VERIFIED_APPLICATION_NOTICES['a307225']
        self.assertEqual(proof['expected_source_seats'], '33')
        self.assertEqual(proof['source_employment'], ['정규직'])
        self.assertEqual(proof['application_start'], '2026-11-19')
        self.assertEqual(proof['application_end_date'], '2026-12-03')
        self.assertEqual(proof['notice_source_sha256'],
                         'a45a7bebec1929e6f18315ee8ace0aa20b59ddf6af5cb40503d206f46faa3cd2')
        self.assertEqual(CONFIRMED_APPLICATION_CUTOFFS['a307225'],
                         '2026-12-03T17:00:00+09:00')
        post = {p['id']: p for p in json.loads(
            Path('alio.json').read_text(encoding='utf-8'))['posts']}['a307225']
        html = render(post, {})
        for phrase in ('간호직30명', '의료사회복지사2명',
                       '보건직 산부인과 방사선사1명', '17시(KST)',
                       '공고 전체 모집정원', '기관 공식 확인 접수마감'):
            self.assertIn(phrase, html)
        self.assertNotIn('2026-12-03 23:59 (KST)', html)

    def test_new_add_162_mixed_and_road_four_are_source_bound(self):
        """Nov 18 official HTML is display evidence, not 162 regular seats or a verified deadline."""
        from datetime import date
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES, CONFIRMED_APPLICATION_CUTOFFS
        from scripts.priority_candidate_audit import shortlist
        cases = [
            (
                'a306990', '국방과학연구소', "국방과학연구소 '27년 상반기 임용 공개채용",
                '162', ['무기계약직', '정규직', '계약직'],
                '공식 JOB-ALIO의 162명은 정규직·무기계약직·비정규직을 합친',
                '정규직 162명 모집으로 해석할 수 없으며',
            ),
            (
                'a307189', '한국도로공사',
                '2026년 한국도로공사 전문연구원(AI·데이터분석) 채용 공고',
                '4', ['무기계약직'],
                '정규직이 아닌 무기계약직 전문연구원 4명',
                '석사 취득 후 해당분야 3년 이상',
            ),
        ]
        posts = []
        for pid, org, title, seats, employment, notice, requirement in cases:
            post = {'id': pid, 'alio': True, 'org': org, 'title': title,
                    'n': seats, 'emp': employment,
                    'due': '2026-12-02T23:59:00+09:00',
                    'dueHasTime': False,
                    'url': f'https://job.alio.go.kr/recruitview.do?idx={pid[1:]}',
                    'region': '경북' if pid == 'a307189' else '전국'}
            original = copy.deepcopy(post)
            proof = VERIFIED_APPLICATION_NOTICES[pid]
            self.assertEqual(proof['expected_source_seats'], post['n'])
            self.assertEqual(proof['source_employment'], post['emp'])
            self.assertNotIn(pid, CONFIRMED_APPLICATION_CUTOFFS)
            self.assertNotIn('application_start', proof)
            html = render(post, {})
            self.assertIn(notice, html)
            self.assertIn(requirement, html)
            self.assertNotIn('기관 공식 확인 접수마감', html)
            for change in ({'n': str(int(seats) + 1)},
                           {'emp': ['정규직'] if pid == 'a307189' else ['정규직']},
                           {'title': title + ' (정정)'}, {'org': '다른 기관'},
                           {'due': '2026-12-03T23:59:00+09:00'},
                           {'alio': False}):
                stale_html = render({**post, **change}, {})
                self.assertNotIn(notice, stale_html)
                self.assertNotIn(requirement, stale_html)
            self.assertEqual(post, original)
            posts.append(post)
        report = shortlist({'posts': posts}, date(2026, 11, 18))
        self.assertEqual(report['regular_review_candidates'], [])
        self.assertEqual(report['top'][0]['id'], 'a306990')
        self.assertTrue(report['top'][0]['mixed_employment_with_regular'])
        self.assertFalse(report['top'][0]['regular_only_classified'])
        self.assertFalse(report['top'][1]['regular_only_classified'])

    def test_source_bound_date_only_reception_end_precedes_later_publication_end(self):
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        from scripts.priority_candidate_audit import shortlist
        from datetime import date
        post = dict(id='a309999', alio=True, org='검증기관', title='접수기간이 더 짧은 공고',
                    n='4', emp=['정규직'], due='2026-12-05T23:59:00+09:00',
                    url='https://job.alio.go.kr/recruitview.do?idx=309999')
        original = copy.deepcopy(post)
        proof = dict(organization=post['org'], title=post['title'],
                     source_end_date='2026-12-05', expected_source_seats='4',
                     source_employment=['정규직'], application_start='2026-11-24',
                     application_end_date='2026-12-01')
        meta = homepage_cutoff_metadata([post], {}, {post['id']: proof})
        self.assertEqual(meta[post['id']]['endDate'], '2026-12-01')
        self.assertEqual(meta[post['id']]['sourceSeats'], '4')
        self.assertEqual(meta[post['id']]['sourceTerms'], ['정규직'])
        before = datetime.fromisoformat('2026-11-30T23:59:59+09:00')
        last_day = datetime.fromisoformat('2026-12-01T00:00:00+09:00')
        next_day = datetime.fromisoformat('2026-12-02T00:00:00+09:00')
        self.assertEqual(static_recruitment_posts([post], meta, before), [post])
        opening_day = datetime.fromisoformat('2026-11-24T12:00:00+09:00')
        after_opening_day = datetime.fromisoformat('2026-11-25T00:00:00+09:00')
        self.assertEqual(static_recruitment_posts([post], meta, opening_day), [])
        self.assertEqual(static_recruitment_posts([post], meta, after_opening_day), [post])
        self.assertEqual(static_recruitment_posts([post], meta, last_day), [])
        self.assertEqual(static_recruitment_posts([post], meta, next_day), [])
        report = shortlist({'posts':[post]}, date(2026,12,2),
                           verified_windows={post['id']:proof})
        self.assertEqual(report['excluded']['official_reception_closed_by_date'], 1)
        for change in ({'n':'5'}, {'emp':['계약직']}, {'title':'정정공고'},
                       {'org':'다른기관'}, {'due':'2026-12-06T23:59:00+09:00'},
                       {'alio':False}):
            self.assertEqual(homepage_cutoff_metadata(
                [{**post, **change}], {}, {post['id']:proof}), {})
        self.assertEqual(post, original)


    def test_kopo_deans_two_year_term_and_official_1800_arrival_cutoff(self):
        from datetime import timedelta
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_APPLICATION_NOTICES
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        # This notice entered main in the latest 1077-post feed; the draft
        # branch retains an older snapshot. Use a faithful isolated fixture.
        post = dict(id='a307171', alio=True, type='j',
                    org='학교법인한국폴리텍',
                    title='한국폴리텍대학 지역대학장(서울강서, 화성, 충주, 울산) 공개초빙 공고',
                    n='4', emp=['정규직'],
                    pub='2026-11-18T00:00:00+09:00',
                    due='2026-11-25T23:59:00+09:00', dueHasTime=False,
                    url='https://job.alio.go.kr/recruitview.do?idx=307171')
        original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES[post['id']]
        cutoff = CONFIRMED_APPLICATION_CUTOFFS[post['id']]
        self.assertEqual(cutoff, '2026-11-25T18:00:00+09:00')
        html = render(post, {})
        self.assertIn('임기는 2년', html)
        self.assertIn('등기우편', html)
        self.assertIn('중복지원은 불가', html)
        self.assertIn('기관 공식 확인 접수마감', html)
        self.assertIn('2026-11-25 18:00 (KST)', html)
        meta = homepage_cutoff_metadata([post], {post['id']: cutoff}, {post['id']: proof})
        self.assertEqual(meta[post['id']]['cutoff'], cutoff)
        before = datetime.fromisoformat(cutoff) - timedelta(seconds=1)
        self.assertEqual(static_recruitment_posts([post], meta, before), [post])
        self.assertEqual(static_recruitment_posts([post], meta, datetime.fromisoformat(cutoff)), [])
        for change in ({'n': '5'}, {'emp': ['계약직']},
                       {'title': '정정공고'}, {'org': '다른기관'},
                       {'due': '2026-11-26T23:59:00+09:00'}, {'alio': False}):
            altered = {**post, **change}
            self.assertNotIn('임기는 2년', render(altered, {}))
            self.assertNotIn('기관 공식 확인 접수마감', render(altered, {}))
            self.assertEqual(homepage_cutoff_metadata([altered],
                {post['id']: cutoff}, {post['id']: proof}), {})
        self.assertEqual(post, original)

    def test_evergreen_unconfirmed_status_is_displayed_and_excluded_on_homepage(self):
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        for pid in ('a292002', 'a305089'):
            post = posts[pid]
            original = copy.deepcopy(post)
            proof = VERIFIED_APPLICATION_NOTICES[pid]
            self.assertTrue(proof['application_status_unconfirmed'])
            self.assertIn('<meta name="robots" content="noindex,follow">', render(post, {}))
            metadata = homepage_cutoff_metadata([post], {}, {pid: proof})
            self.assertIn(pid, metadata)
            self.assertIn('실제 접수 활성 상태', metadata[pid]['statusNote'])
            self.assertEqual(metadata[pid]['sourceSeats'], str(post['n']))
            self.assertEqual(metadata[pid]['sourceTerms'], post['emp'])
            self.assertEqual(static_recruitment_posts(
                [post], metadata, datetime(2026, 11, 18, 4, 20, tzinfo=timezone.utc)), [])
            for changed in ({'title': '정정공고'}, {'org': '변경기관'},
                            {'n': '15'}, {'emp': ['계약직']},
                            {'due': '2026-12-30T23:59:00+09:00'}, {'alio': False}):
                updated = {**post, **changed}
                self.assertNotIn('<meta name="robots" content="noindex,follow">', render(updated, {}))
                self.assertEqual(homepage_cutoff_metadata([updated], {}, {pid: proof}), {})
            self.assertEqual(post, original)

    def test_gnuh_trauma_2025_notice_fourteen_not_verified_live_vacancies(self):
        from datetime import date
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES
        from scripts.priority_candidate_audit import shortlist
        post = next(p for p in json.loads(Path('alio.json').read_text())['posts']
                    if p['id'] == 'a292002')
        original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a292002']
        self.assertEqual(proof['expected_source_seats'], post['n'])
        self.assertTrue(proof['application_status_unconfirmed'])
        html = render(post, {})
        self.assertIn('현재 잔여 채용인원 14명으로 확정할 수 없습니다', html)
        self.assertIn('교육 및 연구경력 통산 4년 이상', html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        report = shortlist({'posts': [post]}, date(2026, 11, 18),
                           verified_windows={'a292002': proof})
        self.assertEqual(report['excluded']['official_current_status_unconfirmed'], 1)
        self.assertEqual(report['regular_review_candidates'], [])
        for changed in ({'title': '정정 공고'}, {'org': '변경 기관'}, {'n': '15'},
                        {'emp': ['계약직']}, {'due': '2026-12-30T23:59:00+09:00'},
                        {'alio': False}):
            altered = {**post, **changed}
            self.assertNotIn('현재 잔여 채용인원 14명으로 확정할 수 없습니다',
                             render(altered, {}))
            revised = shortlist({'posts': [altered]}, date(2026, 11, 18),
                                verified_windows={'a292002': proof})
            self.assertNotIn('official_current_status_unconfirmed', revised['excluded'])
        self.assertEqual(post, original)

    def test_cnuh_evergreen_fourteen_seats_are_not_presented_as_live_vacancies(self):
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES
        post = next(p for p in json.loads(Path('alio.json').read_text())['posts']
                    if p['id'] == 'a305089')
        original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a305089']
        self.assertTrue(proof['application_status_unconfirmed'])
        self.assertEqual(proof['expected_source_seats'], post['n'])
        html = render(post, {})
        self.assertIn('현재 남아 있는 확정 결원 14명이라는 뜻이 아닙니다', html)
        self.assertIn('학위논문은 기간 제한 없음', html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        for changed in ({'n': '15'}, {'org': '다른 기관'}, {'title': '정정 공고'},
                        {'due': '2027-01-01T23:59:00+09:00'},
                        {'emp': ['계약직']}, {'alio': False}):
            changed_html = render({**post, **changed}, {})
            self.assertNotIn('현재 남아 있는 확정 결원 14명이라는 뜻이 아닙니다', changed_html)
        self.assertEqual(post, original)

    def test_cbnuh_official_noon_cutoff_is_source_bound_and_does_not_rewrite_feed(self):
        from datetime import timedelta
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_APPLICATION_NOTICES
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        from scripts.priority_candidate_audit import shortlist
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306665']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306665']
        cutoff = CONFIRMED_APPLICATION_CUTOFFS['a306665']
        self.assertEqual(cutoff, '2026-11-18T12:00:00+09:00')
        self.assertEqual(proof['expected_source_seats'], post['n'])
        self.assertEqual(proof['source_employment'], post['emp'])
        html = render(post, {})
        self.assertIn('2026-11-18 12:00 (KST)', html)
        self.assertIn('공고 전체 모집인원 13명', html)
        self.assertNotIn('기관 공식 확인 접수마감</th><td>2026-11-18 23:59', html)
        meta = homepage_cutoff_metadata([post], {post['id']: cutoff}, {post['id']: proof})
        self.assertEqual(meta['a306665']['cutoff'], cutoff)
        before = datetime.fromisoformat(cutoff) - timedelta(seconds=1)
        instant = datetime.fromisoformat(cutoff)
        self.assertEqual(static_recruitment_posts([post], meta, before), [post])
        self.assertEqual(static_recruitment_posts([post], meta, instant), [])
        window = {post['id']: {**proof, 'application_cutoff': cutoff}}
        self.assertEqual(len(shortlist({'posts': [post]}, instant.date(),
            verified_windows=window, as_of_instant=before)['top']), 1)
        self.assertEqual(shortlist({'posts': [post]}, instant.date(),
            verified_windows=window, as_of_instant=instant)['excluded']['official_reception_closed'], 1)
        for changed in ({'n': '14'}, {'org': '다른기관'}, {'title': '정정공고'},
                        {'emp': ['계약직']}, {'due': '2026-11-19T23:59:00+09:00'},
                        {'alio': False}):
            altered = {**post, **changed}
            self.assertNotIn('공고 전체 모집인원 13명', render(altered, {}))
            self.assertNotIn('기관 공식 확인 접수마감', render(altered, {}))
            self.assertEqual(homepage_cutoff_metadata([altered],
                {post['id']: cutoff}, {post['id']: proof}), {})
        self.assertEqual(post, original)

    def test_wonju_care_actual_1700_cutoff_is_source_bound_and_never_rewrites_feed(self):
        from datetime import timedelta
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_APPLICATION_NOTICES
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306660']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306660']
        cutoff = CONFIRMED_APPLICATION_CUTOFFS['a306660']
        self.assertEqual(cutoff, '2026-11-18T17:00:00+09:00')
        self.assertEqual(proof['expected_source_seats'], post['n'])
        html = render(post, {})
        self.assertIn('2026-11-03 ~ 2026-11-18 17:00 (KST)', html)
        self.assertIn('즉시 임용 예정은 8명', html)
        self.assertIn('요양보호사 자격증', html)
        self.assertNotIn('기관 공식 확인 접수마감</th><td>2026-11-18 23:59', html)
        meta = homepage_cutoff_metadata([post], {post['id']: cutoff}, {post['id']: proof})
        self.assertEqual(meta['a306660']['cutoff'], cutoff)
        self.assertEqual(homepage_cutoff_metadata([{**post, 'n': '13'}],
            {post['id']: cutoff}, {post['id']: proof}), {})
        self.assertEqual(homepage_cutoff_metadata([{**post, 'emp': ['계약직']}],
            {post['id']: cutoff}, {post['id']: proof}), {})
        instant = datetime.fromisoformat(cutoff)
        self.assertEqual(static_recruitment_posts([post], meta, instant - timedelta(seconds=1)), [post])
        self.assertEqual(static_recruitment_posts([post], meta, instant), [])
        for changed in ({'title': '정정'}, {'org': '다른 기관'},
                        {'due': '2026-11-19T23:59:00+09:00'}, {'n': '13'},
                        {'emp': ['계약직']}, {'alio': False}):
            self.assertNotIn('즉시 임용 예정은 8명', render({**post, **changed}, {}))
            self.assertNotIn('기관 공식 확인 접수마감', render({**post, **changed}, {}))
        self.assertEqual(post, original)

    def test_gwangju_veterans_six_role_split_1000_official_cutoff(self):
        from datetime import timedelta
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_APPLICATION_NOTICES
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306718']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306718']
        cutoff = CONFIRMED_APPLICATION_CUTOFFS['a306718']
        self.assertEqual(cutoff, '2026-11-18T10:00:00+09:00')
        self.assertEqual(post['n'], '6')
        self.assertEqual(proof['source_employment'], post['emp'])
        html = render(post, {})
        self.assertIn('2026-11-04 ~ 2026-11-18 10:00 (KST)', html)
        self.assertIn('임상병리사 2명, 간호조무사 3명, 시설 전기 1명', html)
        self.assertIn('전기산업기사', html)
        meta = homepage_cutoff_metadata([post], {post['id']: cutoff}, {post['id']: proof})
        self.assertEqual(meta['a306718']['cutoff'], cutoff)
        at = datetime.fromisoformat(cutoff)
        self.assertEqual(static_recruitment_posts([post], meta, at - timedelta(seconds=1)), [post])
        self.assertEqual(static_recruitment_posts([post], meta, at), [])
        for altered in ({'n': '7'}, {'emp': ['계약직']}, {'title': '수정 공고'},
                        {'org': '다른 기관'}, {'due': '2026-11-19T23:59:00+09:00'},
                        {'alio': False}):
            changed = {**post, **altered}
            self.assertEqual(homepage_cutoff_metadata(
                [changed], {post['id']: cutoff}, {post['id']: proof}), {})
            changed_html = render(changed, {})
            self.assertNotIn('임상병리사 2명, 간호조무사 3명, 시설 전기 1명', changed_html)
            self.assertNotIn('기관 공식 확인 접수마감', changed_html)
        self.assertEqual(post, original)

    def test_snubh_fourteen_roles_split_keeps_six_intern_positions_distinct(self):
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a307074']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a307074']
        self.assertEqual(proof['expected_source_seats'], '14')
        self.assertEqual(proof['source_employment'], ['정규직'])
        html = render(post, {})
        self.assertIn('경력 간호직 6명', html)
        self.assertIn('경력 보건직 2명', html)
        self.assertIn('신입 일반직인턴(보건직) 6명', html)
        self.assertIn('전체14명을 즉시 확정 일반직 정규직 인원으로 단정하지 마세요', html)
        self.assertIn('TOEIC750', html)
        # Only the employer's career-specific eight-role notice confirms this time.
        self.assertIn('경력직 8명 전용 채용공고는 2026-11-17 12:00~11-26 23:59', html)
        self.assertIn('신입 일반직인턴(보건직) 6명의 기관별 실제 접수화면', html)
        self.assertIn('전체 14명 공통 접수마감으로 사용하지 마세요', html)
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS
        self.assertNotIn('a307074', CONFIRMED_APPLICATION_CUTOFFS)
        self.assertNotIn('기관 공식 확인 접수마감', html)  # no global 23:59 cutoff
        for changed in ({'title': '정정'}, {'org': '다른 기관'},
                        {'due': '2026-11-27T23:59:00+09:00'}, {'n': '15'},
                        {'emp': ['무기계약직']}, {'alio': False}):
            updated = render({**post, **changed}, {})
            self.assertNotIn('신입 일반직인턴(보건직) 6명', updated)
            self.assertNotIn('전체14명을 즉시 확정', updated)
            self.assertNotIn('경력직 8명 전용 채용공고는', updated)
        self.assertEqual(post, original)

    def test_new_postal_reception_and_original_identity_guards(self):
        posts={p['id']:p for p in json.loads(Path('alio.json').read_text())['posts']}
        for pid in ['a307150','a307151']:
            post=posts[pid];html=render(post,{})
            self.assertIn('2026-11-24 ~ 2026-12-01 10:00 (KST)',html)
            self.assertIn('11월24일',html)
            for change in [{'title':'정정'},{'due':'2026-12-02'},{'alio':False}]:
                self.assertNotIn('2026-12-01 10:00 (KST)',render({**post,**change},{}))

    def test_snubh_requirements_table_matches_current_source_and_preserves_raw(self):
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        detail = json.loads(Path('alio-detail.json').read_text())['a306875']
        post = posts['a306875']
        originals = copy.deepcopy((post, detail))
        html = render(post, detail)
        self.assertIn('공식 지원자격과 대조한 분야별 인원·필수요건', html)
        self.assertIn('합계는 66명입니다', html)
        self.assertIn('<th scope="row">병동</th><td>50명</td>', html)
        self.assertIn('근무경험만으로 자격증 요건을 대신', html)
        self.assertIn('실제 원서접수 마감시각으로 사용하지 않으며', html)
        self.assertIn('2026-11-11 ~ 2026-11-20 (마감시각 공식 공고 확인 필요)', html)
        self.assertIn('fileNo=3086118', html)
        self.assertEqual((post, detail), originals)

    def test_snubh_requirements_table_rejects_changed_or_wrong_source(self):
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        detail = json.loads(Path('alio-detail.json').read_text())['a306875']
        post = posts['a306875']
        marker = '공식 지원자격과 대조한 분야별 인원·필수요건'
        for revised_post, revised_detail in [
                ({**post, 'n': '65'}, detail),
                ({**post, 'title': '정정채용'}, detail),
                ({**post, 'due': '2026-11-21'}, detail),
                (post, {**detail, 'recrutPblntSn': '999999'}),
                (post, {**detail, 'aplyQlfcCn': detail['aplyQlfcCn'] + '정정'}),
                (post, {**detail, 'aplyQlfcCn': None})]:
            with self.subTest(post=revised_post['title']):
                self.assertNotIn(marker, render(revised_post, revised_detail))

    def test_snudh_alio_qualification_year_conflict_is_source_bound_and_original_preserved(self):
        # ALIO a306925 shows 2026 expected licensure; SNUDH employer 2027
        # internship notice explicitly shows 2027. Do not silently alter raw.
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306925']
        original = copy.deepcopy(post)
        detail = {'recrutPblntSn': '306925',
                  'aplyQlfcCn': '치과의사 면허 취득자 또는 2026년도 취득예정자로서'}
        old_detail = copy.deepcopy(detail)
        html = render(post, detail)
        self.assertIn('기관 공고와 ALIO 지원자격 연도 차이', html)
        self.assertIn('2027년도 취득예정자로 표시됩니다', html)
        self.assertIn('2026년도 취득예정자로서', html)
        self.assertEqual(post, original)
        self.assertEqual(detail, old_detail)
        # Correction or identity change invalidates the old discrepancy.
        revised = render(post, {**detail,
            'aplyQlfcCn': '치과의사 면허 취득자 또는 2027년도 취득예정자로서'})
        self.assertNotIn('기관 공고와 ALIO 지원자격 연도 차이', revised)
        changed = render({**post, 'title': '정정채용'}, detail)
        self.assertNotIn('기관 공고와 ALIO 지원자격 연도 차이', changed)
        wrong_detail = render(post, {**detail, 'recrutPblntSn': '999999'})
        self.assertNotIn('기관 공고와 ALIO 지원자격 연도 차이', wrong_detail)

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

    def test_existing_nurse_originals_get_identity_bound_employer_reception_clocks(self):
        from scripts.build_job_pages import (
            CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_APPLICATION_NOTICES, VERIFIED_DUTIES)
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        cases = (
            ('a306662', '2026-11-03', '2026-11-18T17:00:00+09:00',
             'https://kcch.re.kr/rirams/board/generalBoardView7.do?no=23098'),
            ('a306799', '2026-11-06', '2026-11-23T10:00:00+09:00',
             'https://www.nmc.or.kr/nmc/board/B0000007/28373'),
        )
        for pid, start, cutoff, url in cases:
            with self.subTest(pid=pid):
                post = posts[pid]; original = copy.deepcopy(post)
                proof = VERIFIED_APPLICATION_NOTICES[pid]
                self.assertEqual(proof['source_url'], url)
                self.assertEqual(proof['application_start'], start)
                self.assertEqual(proof['source_end_date'], post['due'][:10])
                self.assertIn(pid, VERIFIED_DUTIES)  # existing PDF review, not new PDF verification
                self.assertEqual(CONFIRMED_APPLICATION_CUTOFFS[pid], cutoff)
                html = render(post, {})
                self.assertIn(f"{start} ~ {cutoff[:16].replace('T', ' ')} (KST)", html)
                self.assertNotIn(cutoff[:10] + ' 23:59 (KST)', html)
                meta = homepage_cutoff_metadata(
                    [post], {pid: cutoff},
                    {pid: {**VERIFIED_DUTIES[pid], **proof}})
                self.assertEqual(meta[pid]['cutoff'], cutoff)
                self.assertEqual(meta[pid]['sourceSeats'], str(post['n']))
                self.assertEqual(meta[pid]['sourceTerms'], post['emp'])
                self.assertEqual(meta[pid]['start'], start)
                at_cutoff = datetime.fromisoformat(cutoff)
                from datetime import timedelta
                self.assertEqual(static_recruitment_posts(
                    [post], meta, at_cutoff - timedelta(seconds=1)), [post])
                self.assertEqual(static_recruitment_posts([post], meta, at_cutoff), [])
                for change in ({'org': 'changed org'}, {'title': 'changed title'},
                               {'due': '2027-02-01T23:59:00+09:00'}, {'alio': False}):
                    changed = dict(post, **change)
                    self.assertEqual(homepage_cutoff_metadata(
                        [changed], {pid: cutoff}, {pid: proof}), {})
                    self.assertNotIn('기관 공식 확인 접수마감', render(changed, {}))
                self.assertEqual(post, original)

    def test_alio_detailed_application_cutoff_is_source_bound_without_duty_pdf_claim(self):
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_APPLICATION_NOTICES, VERIFIED_DUTIES
        from scripts.build_public_site import homepage_cutoff_metadata
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306755']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306755']
        self.assertEqual(proof['source_url'], 'https://job.alio.go.kr/recruitview.do?idx=306755')
        self.assertNotIn('a306755', VERIFIED_DUTIES)
        html = render(post, {})
        self.assertIn('2026-11-20 17:00 (KST)', html)
        self.assertIn('2026-11-05 ~ 2026-11-20 17:00 (KST)', html)
        self.assertNotIn('2026-11-20 23:59', html)
        self.assertEqual(post, original)
        clocks = {'a306755': CONFIRMED_APPLICATION_CUTOFFS['a306755']}
        proof_map = {'a306755': proof}
        meta = homepage_cutoff_metadata([post], clocks, proof_map)
        self.assertEqual(meta['a306755']['cutoff'], '2026-11-20T17:00:00+09:00')
        self.assertEqual(meta['a306755']['start'], '2026-11-05')
        for changes in ({'org': '다른 기관'}, {'title': '다른 공고'}, {'due': '2026-11-21T23:59:00+09:00'}, {'alio': False}):
            altered = dict(post, **changes)
            self.assertEqual(homepage_cutoff_metadata([altered], clocks, proof_map), {})
            self.assertNotIn('기관 공식 확인 접수마감', render(altered, {}))

    def test_snudh_intern_actual_future_reception_is_not_alio_posting_period(self):
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_APPLICATION_NOTICES
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306925']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306925']
        self.assertEqual(post['pub'][:10], '2026-11-11')  # ALIO publication, not application
        self.assertEqual(proof['source_end_date'], post['due'][:10])
        self.assertIn('www.snudh.org/portal/blindEmpmn/view.do', proof['source_url'])
        self.assertEqual(proof['application_start'], '2027-01-18T09:00:00+09:00')
        html = render(post, {})
        self.assertIn('2027-01-18 09:00 ~ 2027-01-22 18:00 (KST)', html)
        self.assertNotIn('2027-01-22 23:59 (KST)', html)
        self.assertNotIn('application/ld+json', html)  # no unverified time schema
        cutoffs = {'a306925': CONFIRMED_APPLICATION_CUTOFFS['a306925']}
        proofs = {'a306925': proof}
        metadata = homepage_cutoff_metadata([post], cutoffs, proofs)
        self.assertEqual(metadata['a306925']['start'], '2027-01-18T09:00:00+09:00')
        self.assertEqual(metadata['a306925']['cutoff'], '2027-01-22T18:00:00+09:00')
        self.assertEqual(static_recruitment_posts([post], metadata, datetime.fromisoformat(
            '2027-01-18T08:59:59+09:00')), [])
        self.assertEqual(static_recruitment_posts([post], metadata, datetime.fromisoformat(
            '2027-01-18T09:00:00+09:00')), [post])
        self.assertEqual(static_recruitment_posts([post], metadata, datetime.fromisoformat(
            '2027-01-22T18:00:00+09:00')), [])
        for change in ({'org': '다른 기관'}, {'title': '다른 공고'},
                       {'due': '2027-01-23T23:59:00+09:00'}, {'alio': False}):
            altered = dict(post, **change)
            self.assertEqual(homepage_cutoff_metadata([altered], cutoffs, proofs), {})
            self.assertNotIn('기관 공식 확인 접수마감', render(altered, {}))
        self.assertEqual(post, original)

    def test_cnuh_dental_intern_reception_window_is_employer_verified_and_not_open_early(self):
        from scripts.build_job_pages import (CONFIRMED_APPLICATION_CUTOFFS,
                                             VERIFIED_APPLICATION_NOTICES, VERIFIED_DUTIES)
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306942']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306942']
        self.assertEqual(post['org'], '전남대학교병원')
        self.assertEqual(post['title'], proof['title'])
        self.assertEqual(proof['source_end_date'], post['due'][:10])
        self.assertEqual(proof['application_start'], '2027-01-18T09:00:00+09:00')
        self.assertIn('jobnoticeSn=271734', proof['source_url'])
        # A pre-existing curriculum HWP is not proof of the actual application time.
        self.assertIn('a306942', VERIFIED_DUTIES)
        html = render(post, {})
        self.assertIn('2027-01-18 09:00 ~ 2027-01-22 17:00 (KST)', html)
        self.assertNotIn('2027-01-22 23:59 (KST)', html)
        clocks = {'a306942': CONFIRMED_APPLICATION_CUTOFFS['a306942']}
        proof_map = {'a306942': proof}
        metadata = homepage_cutoff_metadata([post], clocks, proof_map)
        self.assertEqual(metadata['a306942']['start'], '2027-01-18T09:00:00+09:00')
        self.assertEqual(metadata['a306942']['cutoff'], '2027-01-22T17:00:00+09:00')
        self.assertEqual(static_recruitment_posts([post], metadata, datetime.fromisoformat(
            '2027-01-18T08:59:59+09:00')), [])
        self.assertEqual(static_recruitment_posts([post], metadata, datetime.fromisoformat(
            '2027-01-18T09:00:00+09:00')), [post])
        self.assertEqual(static_recruitment_posts([post], metadata, datetime.fromisoformat(
            '2027-01-22T17:00:00+09:00')), [])
        for changes in ({'org': '다른 기관'}, {'title': '다른 공고'},
                        {'due': '2027-01-23T23:59:00+09:00'}, {'alio': False}):
            changed = dict(post, **changes)
            self.assertEqual(homepage_cutoff_metadata([changed], clocks, proof_map), {})
            self.assertNotIn('기관 공식 확인 접수마감', render(changed, {}))
        self.assertEqual(post, original)

    def test_kiost_official_reception_clock_and_employment_counts_are_source_bound(self):
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_APPLICATION_NOTICES
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306913']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306913']
        self.assertEqual(proof['source_url'], 'https://www.gojobs.go.kr/apmView.do?empmnsn=308183')
        self.assertEqual(post['n'], '23')
        self.assertEqual(proof['hiring_breakdown'], '정규직 9명 · 무기계약직 14명 (합계 23명)')
        html = render(post, {})
        self.assertIn('2026-11-13 ~ 2026-11-26 10:00 (KST)', html)
        self.assertIn('정규직 9명 · 무기계약직 14명 (합계 23명)', html)
        self.assertNotIn('2026-11-26 23:59 (KST)', html)
        cutoffs = {'a306913': CONFIRMED_APPLICATION_CUTOFFS['a306913']}
        proofs = {'a306913': proof}
        metadata = homepage_cutoff_metadata([post], cutoffs, proofs)
        self.assertEqual(metadata['a306913']['cutoff'], '2026-11-26T10:00:00+09:00')
        self.assertEqual(metadata['a306913']['start'], '2026-11-13')
        self.assertEqual(static_recruitment_posts([post], metadata, datetime.fromisoformat(
            '2026-11-26T09:59:59+09:00')), [post])
        self.assertEqual(static_recruitment_posts([post], metadata, datetime.fromisoformat(
            '2026-11-26T10:00:00+09:00')), [])
        for changes in ({'org': '다른 기관'}, {'title': '다른 공고'},
                        {'due': '2026-11-27T23:59:00+09:00'}, {'alio': False}):
            altered = dict(post, **changes)
            self.assertEqual(homepage_cutoff_metadata([altered], cutoffs, proofs), {})
            self.assertNotIn('고용형태별 인원', render(altered, {}))
            self.assertNotIn('기관 공식 확인 접수마감', render(altered, {}))
        self.assertEqual(post, original)

    def test_eastwest_307149_official_reception_dates_preserve_unknown_clock(self):
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES, CONFIRMED_APPLICATION_CUTOFFS
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        pid = 'a307149'
        proof = VERIFIED_APPLICATION_NOTICES[pid]
        post = {
            'id': pid, 'alio': True, 'org': '한국동서발전(주)',
            'title': '한국동서발전(주) 2027년 상반기 신입직원(대졸수준(일반/보훈) 및 고졸) 선발',
            'pub': '2026-11-17T00:00:00+09:00',
            'due': '2026-12-01T23:59:00+09:00',
            'dueHasTime': False, 'n': '101', 'emp': ['정규직'],
            'url': 'https://job.alio.go.kr/recruitview.do?idx=307149',
        }
        before = copy.deepcopy(post)
        self.assertEqual(proof['source_url'], post['url'])
        self.assertEqual(proof['expected_source_seats'], post['n'])
        self.assertEqual(proof['source_employment'], post['emp'])
        self.assertEqual(proof['application_start'], '2026-11-24')
        self.assertEqual(proof['application_end_date'], '2026-12-01')
        self.assertNotIn(pid, CONFIRMED_APPLICATION_CUTOFFS)
        html = render(post, {})
        self.assertIn('2026-11-24 ~ 2026-12-01 (마감시각 공식 공고 확인 필요)', html)
        self.assertIn('대졸수준 일반전형, 대졸수준 보훈전형', html)
        self.assertIn('TOEIC 700점 이상', html)
        self.assertIn('입사일이 2026년 3월 15일로 표기', html)
        self.assertNotIn('기관 공식 확인 접수마감', html)
        self.assertNotIn('2026-12-01 23:59 (KST)', html)
        self.assertNotIn('type="application/ld+json"', html)
        meta = homepage_cutoff_metadata([post], {}, {pid: proof})
        self.assertEqual(meta[pid]['start'], '2026-11-24')
        self.assertEqual(meta[pid]['endDate'], '2026-12-01')
        self.assertNotIn('cutoff', meta[pid])
        self.assertEqual(static_recruitment_posts(
            [post], meta, datetime.fromisoformat('2026-11-23T23:59:59+09:00')), [])
        # Date-only evidence must not generate a fabricated 00:00/23:59 cutoff.
        for change in ({'org': '다른 기관'}, {'title': '변경 공고'},
                       {'due': '2026-12-02T23:59:00+09:00'}, {'alio': False},
                       {'n': '102'}, {'emp': ['계약직']}):
            altered = dict(post, **change)
            self.assertEqual(homepage_cutoff_metadata([altered], {}, {pid: proof}), {})
            self.assertNotIn('2026-11-24 ~ 2026-12-01', render(altered, {}))
            self.assertNotIn('TOEIC 700점 이상', render(altered, {}))
        self.assertEqual(post, before)

    def test_nps_original_pdf_confirms_contract_and_exact_cutoff_without_raw_changes(self):
        from scripts.build_job_pages import VERIFIED_APPLICATION_NOTICES, CONFIRMED_APPLICATION_CUTOFFS
        from scripts.build_public_site import homepage_cutoff_metadata
        posts = {p['id']: p for p in json.loads(Path('alio.json').read_text())['posts']}
        post = posts['a306988']; original = copy.deepcopy(post)
        proof = VERIFIED_APPLICATION_NOTICES['a306988']
        html = render(post, {})
        self.assertIn('각1명의 계약직', html)
        self.assertIn('2026-12-01 18:00 (KST)', html)
        self.assertIn('공식 공고문 고용형태', html)
        self.assertNotIn('2026-12-01 23:59 (KST)', html)
        metadata = homepage_cutoff_metadata([post], CONFIRMED_APPLICATION_CUTOFFS, {'a306988': proof})
        self.assertEqual(metadata['a306988']['employment']['terms'], ['계약직'])
        for change in ({'org': '다른 기관'}, {'title': '정정 공고'}, {'due': '2026-12-02'}, {'alio': False}):
            revised = dict(post, **change)
            self.assertEqual(homepage_cutoff_metadata([revised], CONFIRMED_APPLICATION_CUTOFFS, {'a306988': proof}), {})
            self.assertNotIn('2026-12-01 18:00 (KST)', render(revised, {}))
        self.assertEqual(post, original)

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
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS, VERIFIED_DUTIES, VERIFIED_APPLICATION_NOTICES
        root = Path(__file__).resolve().parents[1]
        posts = json.loads((root / 'alio.json').read_text())['posts']
        original = copy.deepcopy(posts)
        result = homepage_cutoff_metadata(posts, CONFIRMED_APPLICATION_CUTOFFS,
                                          {**VERIFIED_DUTIES, **VERIFIED_APPLICATION_NOTICES})
        expected = set(CONFIRMED_APPLICATION_CUTOFFS) | {'a306929', 'a306963', 'a306875', 'a306874', 'a306992', 'a307017', 'a292472', 'a299412', 'a292002', 'a305089', 'a306182'}
        if any(p.get('id') == 'a307149' for p in posts):
            expected.add('a307149')
        if any(p.get('id') == 'a306988' for p in posts):
            expected.add('a306988')  # employer-confirmed date-only window, no invented clock
        expected.add('a307251')
        self.assertEqual(set(result), expected)
        # Unverified current reception is not a confirmed application cutoff.
        self.assertIn('a307251', result)
        self.assertNotIn('cutoff', result['a307251'])
        for pid in ('a292002', 'a305089', 'a306182', 'a307251'):
            self.assertIn('실제 접수 활성 상태', result[pid]['statusNote'])
            post = next(p for p in posts if p['id'] == pid)
            self.assertEqual(result[pid]['sourceSeats'], str(post['n']))
            self.assertEqual(result[pid]['sourceTerms'], post['emp'])
        self.assertEqual(result['a306875']['endDate'], '2026-11-20')
        self.assertNotIn('cutoff', result['a306875'])
        self.assertEqual(result['a306874']['endDate'], '2026-11-20')
        self.assertNotIn('cutoff', result['a306874'])
        self.assertEqual(result['a306992']['endDate'], '2026-11-20')
        self.assertNotIn('cutoff', result['a306992'])
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
            if evidence.get('strict_source_identity'):
                post.update(alio=True, due=evidence['source_end_date'])
                if evidence.get('source_employment'):
                    post['emp'] = evidence['source_employment'][:]
                if evidence.get('expected_source_seats') is not None:
                    post['n'] = evidence['expected_source_seats']
            html = render(post, {})
            self.assertIn(html_escape(evidence['summary']), html)
            self.assertIn('공식 직무기술서에서 확인한 담당업무', html)
            self.assertIn(evidence['source_url'], html)
            self.assertIn(evidence['checked_on'], html)
            unrelated = render(dict(post, title='다른 모집분야'), {})
            self.assertNotIn(html_escape(evidence['summary']), unrelated)
            wrong_org = render(dict(post, org='다른 기관'), {})
            self.assertNotIn(html_escape(evidence['summary']), wrong_org)

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
        self.assertEqual(len(self.reviews), 56)
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


class DuplicateRelatedNoticeTests(unittest.TestCase):
    def test_same_notice_is_not_presented_as_separate_recruitment(self):
        from scripts.notice_review import load
        posts={p['id']:p for p in json.loads(Path('alio.json').read_text())['posts']}
        details=json.loads(Path('alio-detail.json').read_text());reviews=load(Path('.'))
        for pid, peer in [('a305959','a306724'),('a306724','a305959')]:
            html=render(posts[pid],details[pid],[posts[peer]],reviews[pid])
            self.assertIn('유사 공고 구분 안내',html)
            self.assertNotIn('같은 기관의 다른 채용공고',html)
            self.assertIn(peer+'.html',html)

class CorrectedAndSharedOriginalTests(unittest.TestCase):
    def setUp(self):
        from scripts.notice_review import load
        self.posts={p['id']:p for p in json.loads(Path('alio.json').read_text())['posts']}
        self.details=json.loads(Path('alio-detail.json').read_text())
        self.reviews=load(Path('.'))

    def test_cancelled_postal_position_is_a_revision_not_additional_recruitment(self):
        for pid,number in [('a306334','23'),('a306653','22')]:
            self.assertEqual(self.reviews[pid]['decision'],'amended_notice')
            post=self.posts[pid];before=copy.deepcopy(post)
            peer='a306653' if pid=='a306334' else 'a306334'
            html=render(post,self.details[pid],[self.posts[peer]],self.reviews[pid])
            self.assertIn('부평우체국 금융경비 1명',html)
            self.assertIn('2026-11-09 18:00 (KST)',html)
            self.assertIn('meta name="robots" content="noindex,follow"',html)
            self.assertIn('rel="canonical" href="https://kllollain-max.github.io/careerpick/jobs/'+pid+'.html"',html)
            self.assertNotIn('같은 기관의 다른 채용공고',html)
            self.assertNotIn('동일 채용의 대표 공고 보기',html)
            self.assertEqual(post['n'],number)
            self.assertEqual(post,before)

    def test_identical_hwp_does_not_collapse_different_start_date_positions(self):
        from scripts.notice_review import resolve
        rules=json.loads(Path('scripts/verified_notice_reviews.json').read_text())
        pair=next(r for r in rules if r['members'][0]['id']=='a306548')
        self.assertEqual([s['sha256'] for s in pair['members'][0]['sources']],[s['sha256'] for s in pair['members'][1]['sources']])
        for pid,date in [('a306548','2026년 12월 1일'),('a306553','2027년 1월 1일')]:
            html=render(self.posts[pid],self.details[pid],notice_review=self.reviews[pid])
            self.assertIn(date,html)
            self.assertIn('요양보호사는 총 2명',html)
            self.assertIn('별도 간호사(비정규직)',html)
            self.assertIn('2026-11-17 17:00 (KST)',html)
            self.assertNotIn('2026-11-17 23:59',html)
            self.assertNotIn('동일 채용의 대표 공고 보기',html)
            self.assertIn('jobs/'+pid+'.html',html)
        changed=copy.deepcopy(self.details);changed['a306553']['aplyQlfcCn']='changed appointment'
        self.assertNotIn('a306548',resolve(list(self.posts.values()),changed))

    def test_confirmed_clock_closes_exactly_at_cutoff(self):
        from scripts import build_job_pages as pages
        from datetime import timedelta
        cutoff=datetime.fromisoformat('2026-11-17T17:00:00+09:00')
        class Clock(datetime):
            moment=cutoff
            @classmethod
            def now(cls,tz=None):return cls.moment.astimezone(tz)
        with patch.object(pages,'datetime',Clock):
            Clock.moment=cutoff-timedelta(seconds=1)
            self.assertFalse(pages.is_closed(pages.CONFIRMED_APPLICATION_CUTOFFS['a306548']))
            Clock.moment=cutoff
            self.assertTrue(pages.is_closed(pages.CONFIRMED_APPLICATION_CUTOFFS['a306548']))
            html=render(self.posts['a306548'],self.details['a306548'])
            self.assertIn('meta name="robots" content="noindex,follow"',html)
            self.assertIn('noindex',html)
            self.assertNotIn('application/ld+json',html)

    def test_source_duties_are_limited_to_the_verified_role(self):
        html=render(self.posts['a306548'],self.details['a306548'])
        self.assertIn('생활·돌봄 일지와 소모품 기록',html)
        self.assertIn('간호사 업무 제외',html)
        postal=render(self.posts['a306653'],self.details['a306653'])
        self.assertIn('기술원 항목',postal)
        self.assertIn('모든 모집분야 공통 업무가 아님',postal)

class RemainingOriginalReviewTests(unittest.TestCase):
    def setUp(self):
        from scripts.notice_review import load
        self.posts={p['id']:p for p in json.loads(Path('alio.json').read_text())['posts']}
        self.details=json.loads(Path('alio-detail.json').read_text())
        self.reviews=load(Path('.'))

    def test_single_notice_comparison_cannot_enable_duplicate_canonical(self):
        from scripts.notice_review import resolve
        rules=json.loads(Path('scripts/verified_notice_reviews.json').read_text())
        row=next(r for r in rules if r['members'][0]['id']=='a293321')
        self.assertEqual(len(row['members'][0]['sources']),1)
        self.assertIn('a293321',self.reviews)
        changed=copy.deepcopy(row);changed['decision']='same_notice';changed['representative_id']='a304271'
        same_source=changed['members'][0]['sources']
        for m in changed['members']:m['sources']=copy.deepcopy(same_source)
        self.assertNotIn('a293321',resolve(list(self.posts.values()),self.details,[changed]))

    def test_same_originals_have_representatives_without_merging_other_versions(self):
        for old,new in [('a306512','a306648'),('a306929','a306963')]:
            html=render(self.posts[old],self.details[old],notice_review=self.reviews[old])
            self.assertIn('rel="canonical" href="https://kllollain-max.github.io/careerpick/jobs/'+new+'.html"',html)
            self.assertIn('동일 채용의 대표 공고 보기',html)
        for pid in ['a306858','a306869','a294622','a305301']:
            html=render(self.posts[pid],self.details[pid],notice_review=self.reviews[pid])
            self.assertIn('rel="canonical" href="https://kllollain-max.github.io/careerpick/jobs/'+pid+'.html"',html)
            self.assertNotIn('동일 채용의 대표 공고 보기',html)
        self.assertNotIn('id="notice-review"',render(self.posts['a294622'],self.details['a294622'],notice_review=self.reviews['a294622']))

    def test_reviewed_source_display_corrects_only_the_unchanged_exact_field(self):
        for old,new,field in [('a306512','a306648','aplyQlfcCn'),('a306929','a306963','disqlfcRsn')]:
            source=copy.deepcopy(self.details[old]);before=copy.deepcopy(source)
            html=render(self.posts[old],source)
            section_id='detail-'+field.lower()
            section=html.split('id="'+section_id+'"',1)[1].split('</section>',1)[0]
            if field=='disqlfcRsn':
                self.assertIn('2027. 3. 1.',section)
                self.assertNotIn('2026. 3. 1.',section)
            else:
                self.assertNotIn('만 60세 이상인 자는 지원 불가',section)
            self.assertEqual(source,before)
            source[field]='changed source must survive'
            self.assertIn('changed source must survive',render(self.posts[old],source))
            source[field]=before[field]
            mismatch=dict(self.posts[old],title='different source notice')
            if field=='disqlfcRsn':self.assertIn('2026. 3. 1.',render(mismatch,source))

    def test_date_only_application_period_never_invents_a_clock(self):
        from scripts.build_job_pages import CONFIRMED_APPLICATION_CUTOFFS
        for pid in ['a306929','a306963']:
            html=render(self.posts[pid],self.details[pid])
            self.assertIn('2027-01-18 ~ 2027-01-22 (마감시각 공식 공고 확인 필요)',html)
            self.assertNotIn(pid,CONFIRMED_APPLICATION_CUTOFFS)
            self.assertNotIn('2027-01-22 23:59',html)
            self.assertNotIn('application/ld+json',html)
            self.assertIn('세부 진료행위 미기재',html)

    def test_nursing_duties_and_public_notice_are_independently_verified(self):
        from scripts.build_job_pages import VERIFIED_DUTIES
        evidence=VERIFIED_DUTIES['a306545']
        self.assertIn('3084175',evidence['source_url'])
        self.assertEqual(evidence['notice_source_url'],'https://job.alio.go.kr/recruitview.do?idx=306545')
        html=render(self.posts['a306545'],self.details['a306545'])
        self.assertIn('2026-11-17 17:00 (KST)',html)
        self.assertIn('외래 진료 동행',html)
        self.assertIn('간호사 1명',html)
        self.assertIn('요양보호사 업무 제외',html)

class DetailDisplayMetadataTests(unittest.TestCase):
    def test_export_requires_exact_identity_source_end_and_supported_field(self):
        from scripts.build_public_site import homepage_detail_corrections
        post=dict(id='a1',alio=True,org='기관',title='공고',due='2027-01-22',
                  n='28',emp=['정규직'])
        proof=dict(organization='기관',title='공고',source_end_date='2027-01-22',detail_display_corrections={'disqlfcRsn':{'expected':'old','value':'checked'},'recrutNope':{'expected':'1','value':'2'}})
        before=copy.deepcopy((post,proof))
        got=homepage_detail_corrections([post],{'a1':proof},{})
        self.assertEqual(set(got['a1']['corrections']),{'disqlfcRsn'})
        self.assertEqual(got['a1']['sourceSeats'],'28')
        self.assertEqual(got['a1']['sourceTerms'],['정규직'])
        self.assertEqual((post,proof),before)
        for malformed in [{'n':None},{'emp':None}]:
            self.assertEqual(homepage_detail_corrections([dict(post,**malformed)],{'a1':proof},{}),{})
        for change in [{'title':'changed'},{'org':'other'},{'due':'2027-01-23'},{'alio':False}]:
            self.assertEqual(homepage_detail_corrections([dict(post,**change)],{'a1':proof},{}),{})

class DateOnlyReceptionMetadataTests(unittest.TestCase):
    def test_date_only_window_filters_future_static_list_without_a_fake_cutoff(self):
        from scripts.build_public_site import homepage_cutoff_metadata, static_recruitment_posts
        post=dict(id='a1',alio=True,org='기관',title='공고',due='2027-01-22')
        proof=dict(organization='기관',title='공고',source_end_date='2027-01-22',application_start='2027-01-18',application_end_date='2027-01-22')
        meta=homepage_cutoff_metadata([post],{}, {'a1':proof})
        self.assertNotIn('cutoff',meta['a1'])
        self.assertEqual(static_recruitment_posts([post],meta,datetime.fromisoformat('2027-01-17T23:59:59+09:00')),[])
        self.assertEqual(static_recruitment_posts([post],meta,datetime.fromisoformat('2027-01-18T00:00:00+09:00')),[])
        self.assertEqual(static_recruitment_posts([post],meta,datetime.fromisoformat('2027-01-18T18:00:00+09:00')),[])
        self.assertEqual(static_recruitment_posts([post],meta,datetime.fromisoformat('2027-01-19T00:00:00+09:00')),[post])
        for change in [{'title':'changed'},{'due':'2027-01-23'}]:
            self.assertEqual(homepage_cutoff_metadata([dict(post,**change)],{}, {'a1':proof}),{})
