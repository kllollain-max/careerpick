"""Regression tests for CareerPick generated ALIO job pages.

Run: python -m unittest discover -s tests -p 'test_job_pages.py'
"""
import unittest
import copy
import json
import re
import tempfile
from pathlib import Path

from scripts.build_job_pages import render


class JobPageTests(unittest.TestCase):
    def setUp(self):
        self.post = {
            'id': 'a123456',
            'alio': True,
            'title': '채용 공고 테스트',
            'org': '테스트 기관',
            'due': '2026-12-31',
            'pub': '2026-10-23',
            'emp': '정규직',
            'region': '강원',
            'desc': '실제 담당 업무와 필요한 역량을 안내하는 테스트용 채용공고입니다.',
            'src': 'https://example.org/jobs/123',
        }

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


