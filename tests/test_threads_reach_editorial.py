"""The reviewed hook must survive the real compact publication boundary."""
from copy import deepcopy
import unittest

from scripts.threads_auto import master_public_copy, COMPACT_STYLE
from scripts.threads_reach_editorial import POLICY_ID, public_pair, balanced_hook_type
from scripts.threads_writer_queue import CTA, QueueValidationError, fingerprint, validate_entry
from tests import test_threads_writer_queue as queue_fixtures


class ReachPublicationTests(unittest.TestCase):
    def setUp(self):
        f = queue_fixtures.WriterQueueTests(); f.setUp()
        self.f = f
        f.policy['publication_style'] = COMPACT_STYLE
        f.policy['editorial_policy'] = {'id': POLICY_ID, 'sha256': 'c' * 64,
            'effective_at': '2026-11-06T10:00:00+09:00', 'grandfathered_entry_sha256': []}
        self.old = deepcopy(f.entry)
        e = f.entry
        e.update(editorial_policy_id=POLICY_ID, editorial_policy_sha256='c' * 64,
                 prepared_at=f.now.isoformat())
        e['image_job']['title'] = '정보보안 담당자'
        candidates = [
            {'id': 'org', 'type': 'A', 'text': '예시연구원 정보보안 담당자 정규직 3명을 뽑아요.'},
            {'id': 'reader', 'type': 'B', 'text': '정보보안 기사 자격이 있다면 예시연구원 정보보안 담당자 정규직 채용을 확인해요.'},
            {'id': 'feature', 'type': 'feature', 'text': '11월 18일 마감하는 예시연구원 정보보안 담당자 정규직 채용이에요.'},
        ]
        review = e['writer']['review']
        ref = review['source_refs'][0]['ref']
        excerpt = '정보보안 담당자 정규직 3명, 정보보안 기사 자격증 소지자'
        review['source_refs'][0]['excerpt'] = excerpt
        review['fact_evidence'] = [
            {'field': 'title', 'value': '정보보안 담당자', 'source_ref': ref, 'excerpt': excerpt},
            {'field': 'count', 'value': 3, 'source_ref': ref, 'excerpt': excerpt},
        ]
        self.metadata = {'policy_id': POLICY_ID, 'candidate_first_sentences': candidates,
            'selected_candidate_id': 'org', 'hook_type': 'A', 'first_sentence': candidates[0]['text'],
            'experiment_eligible': True, 'selection_reason': '고용형태와 직무를 먼저 제시하는 A형 비교',
            'recruitment_unit': {'title': '정보보안 담당자', 'count': 3, 'employment': '정규직'},
            'restrictions_checked': True,
            'key_restrictions': [{'text': '정보보안 기사 자격이 필요해요.', 'source_ref': ref, 'excerpt': excerpt}],
            'fact_consistency_check': 'passed'}
        review['reach_editorial'] = self.metadata
        self.set_hook('A')

    def set_hook(self, kind):
        item = next(c for c in self.metadata['candidate_first_sentences'] if c['type'] == kind)
        self.metadata.update(selected_candidate_id=item['id'], hook_type=kind, first_sentence=item['text'])
        self.f.entry['writer']['post_text'] = item['text'] + '\n\n업무: 정보보안 관리 업무를 담당해요.\n자격: 정보보안 기사 자격이 필요해요.\n\n서류와 지원 자격을 공식 공고에서 확인해요.\n\n' + CTA
        a, b = public_pair(self.f.entry['writer']['post_text'], self.f.entry['image_job'], self.metadata)
        self.metadata['public_preview'] = {'main_text': a, 'detail_reply': b}

    def validated(self):
        f = self.f
        return validate_entry(f.entry, f.slot, f.now, f.history, f.source, f.details, f.policy)

    def test_ab_remain_different_in_final_main_and_detail_is_additional(self):
        final = []
        for kind in ('A', 'B'):
            self.set_hook(kind)
            main, reply = master_public_copy(self.validated(), COMPACT_STYLE)
            final.append(main.splitlines()[0])
            self.assertEqual(main, self.metadata['public_preview']['main_text'])
            self.assertEqual(main.splitlines()[0], self.metadata['first_sentence'])
            self.assertIn('정보보안 기사 자격이 필요해요.', main)
            self.assertNotIn(self.metadata['first_sentence'], reply)
            self.assertEqual(main.count(CTA), 1)
            self.assertNotIn(CTA, reply)
            self.assertLessEqual(len(main), 450)
        self.assertNotEqual(*final)

    def test_final_preview_tamper_blocks_publication(self):
        self.metadata['public_preview']['main_text'] = '정형 문장으로 덮어쓴 본문'
        with self.assertRaisesRegex(QueueValidationError, 'EDITORIAL_PUBLIC_PREVIEW_MISMATCH'):
            self.validated()

    def test_future_prepared_at_is_not_current_verification(self):
        self.f.entry['prepared_at'] = '2026-11-07T10:00:00+09:00'
        with self.assertRaisesRegex(QueueValidationError, 'EDITORIAL_PREPARED_AT_INVALID'):
            self.validated()

    def test_notice_total_excerpt_without_unit_name_is_rejected(self):
        review = self.f.entry['writer']['review']
        review['source_refs'][0]['excerpt'] += '\n공고 전체 총 3명'
        review['fact_evidence'][1]['excerpt'] = '공고 전체 총 3명'
        with self.assertRaisesRegex(QueueValidationError, 'EDITORIAL_UNIT_COUNT_SCOPE_REQUIRED'):
            self.validated()

    def test_relabeling_same_hook_is_not_an_ab_comparison(self):
        self.metadata['hook_type'] = 'B'
        with self.assertRaisesRegex(QueueValidationError, 'EDITORIAL_FINAL_HOOK_MISMATCH'):
            self.validated()

    def test_notice_total_requires_explicit_unit_count_evidence(self):
        self.f.entry['writer']['review']['fact_evidence'] = self.f.entry['writer']['review']['fact_evidence'][:1]
        with self.assertRaisesRegex(QueueValidationError, 'EDITORIAL_UNIT_COUNT_EVIDENCE_REQUIRED'):
            self.validated()

    def test_only_exact_legacy_hash_is_preserved(self):
        f = self.f
        f.policy['editorial_policy']['grandfathered_entry_sha256'] = [fingerprint(self.old)]
        old = validate_entry(self.old, f.slot, f.now, f.history, f.source, f.details, f.policy)
        main, reply = master_public_copy(old, COMPACT_STYLE)
        self.assertTrue(main.startswith('🏢 예시연구원'))
        modified = deepcopy(self.old)
        modified['writer']['review']['target_reader'] += ' 변경'
        with self.assertRaisesRegex(QueueValidationError, 'EDITORIAL_POLICY_REQUIRED'):
            validate_entry(modified, f.slot, f.now, f.history, f.source, f.details, f.policy)

    def test_restrictions_cannot_exist_only_in_unreviewed_main_copy(self):
        self.metadata['key_restrictions'][0]['text'] = '학력 제한이 전혀 없어요.'
        with self.assertRaisesRegex(QueueValidationError, 'EDITORIAL_RESTRICTION_COPY_MISMATCH'):
            self.validated()

    def test_four_day_assignment_balances_each_slot(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        start = datetime(2026, 11, 9, tzinfo=ZoneInfo('Asia/Seoul'))
        for hour in (8, 12, 16, 20):
            assigned = [balanced_hook_type((start + timedelta(days=d)).replace(hour=hour), start.date()) for d in range(4)]
            self.assertEqual(assigned.count('A'), 2)
            self.assertEqual(assigned.count('B'), 2)


if __name__ == '__main__':
    unittest.main()
