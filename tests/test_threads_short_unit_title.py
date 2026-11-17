"""Short real unit names still require exact source-row title/count proof."""
import unittest
from scripts.threads_writer_queue import _image, QueueValidationError


class ShortUnitTitleTests(unittest.TestCase):
    def setUp(self):
        self.job = dict(id='a700', org='병원', title='병동', count=50,
                        employment='정규직', location='경기', due='2026-11-20',
                        deadline_label='2026-11-20 23:59')
        self.detail = dict(instNm='병원', recrutPbancTtl='신입 업무지원직 채용',
                           recrutNope=66, hireTypeNmLst='정규직', workRgnNmLst='경기')
        row = '병동 AA1 50 의료기관 또는 기업체 근무경험 6개월 이상'
        self.refs = [dict(url='https://hospital.example/official', evidence=row)]
        self.review = dict(fact_evidence=[dict(field='title', value='병동',
            source_ref=self.refs[0]['url'], excerpt=row), dict(field='count', value=50,
            source_ref=self.refs[0]['url'], excerpt=row)], v5=dict(contract_version=2,
            recruitment_unit=dict(title='병동', count=50, employment='정규직',
                source_ref=self.refs[0]['url'], excerpt=row, scope='single_recruitment_unit')))

    def validate(self):
        return _image(dict(notice_id='a700', image_job=self.job), {}, self.detail,
            self.review, self.refs, '2026-11-20', dict(end='2026-11-20T23:59:00+09:00',
            date_only=False), False, {})

    def test_exact_two_character_unit_is_accepted(self):
        self.assertEqual(self.validate()['count'], 50)

    def test_notice_total_cannot_replace_unit_count(self):
        self.job['count'] = self.review['v5']['recruitment_unit']['count'] = 66
        with self.assertRaisesRegex(QueueValidationError, 'UNIT_COUNT_BECAME_NOTICE_TOTAL'):
            self.validate()

    def test_short_title_without_independent_fact_is_rejected(self):
        self.review['fact_evidence'] = []
        with self.assertRaisesRegex(QueueValidationError, 'IMAGE_TITLE_INVALID'):
            self.validate()

    def test_unit_scope_cannot_be_notice_total(self):
        self.review['v5']['recruitment_unit']['scope'] = 'notice_total'
        with self.assertRaisesRegex(QueueValidationError, 'RECRUITMENT_UNIT_EVIDENCE'):
            self.validate()

    def test_unretained_source_row_is_rejected(self):
        self.refs[0]['evidence'] = '외래 AA1 3'
        with self.assertRaises(QueueValidationError):
            self.validate()

    def test_legacy_short_title_remains_rejected(self):
        self.review.pop('v5')
        with self.assertRaisesRegex(QueueValidationError, 'IMAGE_TITLE_INVALID'):
            self.validate()

    def test_one_character_label_remains_rejected(self):
        self.job['title'] = '병'
        with self.assertRaisesRegex(QueueValidationError, 'IMAGE_TITLE_INVALID'):
            self.validate()
