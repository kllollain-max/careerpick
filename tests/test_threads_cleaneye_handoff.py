"""Prevent Cleaneye candidates disappearing between selection and draft review."""
from copy import deepcopy
import unittest
from scripts.threads_queue_bridge import review_period
from scripts.threads_unreviewed_drafts import build_drafts


class CleaneyeHandoffTests(unittest.TestCase):
    def setUp(self):
        self.period = {'start': '2026-11-09', 'end': '2026-11-19',
                       'start_date_only': True, 'date_only': True}
        self.item = {'source': 'cleaneye', 'notice_id': 'cleaneye-80820',
                     'source_detail': {'접수개시일 원문': '2026-11-09', '접수마감일 원문': '2026-11-19'},
                     'selection_context': {'application_period': self.period}}

    def test_exact_saved_period_reaches_unreviewed_draft_without_approval(self):
        period = review_period(self.item)
        self.assertNotIn('source_ref', self.period)  # no source mutation
        candidate = {'notice_id': 'cleaneye-80820', 'org': '서울교통공사', 'title': '공무직 공개채용',
                     'employment': '일반정규직', 'application_period': period,
                     'application_source_ref': period['source_ref'], 'application_evidence': period['evidence'],
                     'source_post_sha256': 'a'*64, 'source_detail_sha256': 'b'*64,
                     'official_url': 'https://job.cleaneye.go.kr/user/ypCareersData.do?idx=80820'}
        result = build_drafts({'automatic_approval': False, 'meta_posted': False,
                               'missing_slots': ['2026-11-16T20:00:00+09:00'], 'candidates': [candidate]})
        self.assertEqual(len(result['drafts']), 1)
        draft = result['drafts'][0]
        self.assertFalse(draft['approved_for_queue'])
        self.assertEqual(draft['status'], 'unreviewed')
        self.assertIn('마감 시각 원문 확인', draft['draft_text'])
        self.assertNotIn('23:59', draft['draft_text'])
        self.assertFalse(result['approved_for_queue'])

    def test_mismatched_dates_and_fabricated_clocks_get_no_provenance(self):
        for key, value in [('end', '2026-11-20'), ('end', '2026-11-19T23:59:59+09:00'), ('date_only', False)]:
            item = deepcopy(self.item)
            item['selection_context']['application_period'][key] = value
            self.assertNotIn('evidence', review_period(item))

    def test_saved_timestamp_preserves_its_exact_clock(self):
        item = deepcopy(self.item)
        item['source_detail']['접수마감일 원문'] = '2026-11-19T17:00:00+09:00'
        item['selection_context']['application_period'].update(end='2026-11-19T17:00:00+09:00', date_only=False)
        period = review_period(item)
        self.assertFalse(period['date_only'])
        self.assertEqual(period['end'], '2026-11-19T17:00:00+09:00')
        self.assertIn('17:00:00+09:00', period['evidence'])

    def test_alio_and_existing_review_provenance_are_preserved(self):
        item = deepcopy(self.item); item['source'] = 'alio'
        self.assertEqual(review_period(item), self.period)
        self.item['selection_context']['application_period'].update(source_ref='actual-review', evidence='actual-excerpt')
        self.assertEqual(review_period(self.item)['source_ref'], 'actual-review')

if __name__ == '__main__':
    unittest.main()
