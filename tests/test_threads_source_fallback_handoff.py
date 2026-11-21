"""Exercise the capped-selection to official-evidence outage recovery path."""
from copy import deepcopy
from datetime import datetime
import unittest
from unittest.mock import patch
import urllib.error

from scripts import threads_queue_bridge as bridge
from scripts.threads_candidate_selection import build_selection
from scripts.threads_official_review_pack import (
    CANONICAL_REVIEW_URLS, build_packet, independently_located_notice,
)
from scripts.threads_unreviewed_drafts import build_drafts
from tests.test_threads_cleaneye import cleaneye_post, feed
from tests.test_threads_writer_queue import WriterQueueTests


class SourceFallbackHandoffTests(unittest.TestCase):
    def setUp(self):
        self.fixture = WriterQueueTests()
        self.fixture.setUp()
        f = self.fixture
        f.source['_cleaneye'] = feed(*[cleaneye_post(str(800 + i)) for i in range(60)])
        f.source['posts'] = []
        f.details = {}
        # These lower-ranked but independently source-eligible ALIO notices
        # must not displace the sixty preferred editorial candidates.
        for i in range(10):
            nid = str(700 + i)
            post = {**f.post, 'id': 'a' + nid, 'url': 'https://job.alio.go.kr/recruitview.do?idx=' + nid,
                    'title': '별도 기간제 채용 ' + nid, 'emp': ['비정규직']}
            detail = {**f.detail, 'recrutPblntSn': nid, 'recrutPbancTtl': post['title'],
                      'hireTypeNmLst': '비정규직'}
            f.source['posts'].append(post)
            f.details[post['id']] = detail

    def select(self, **kwargs):
        f = self.fixture
        return build_selection(f.source, f.details, f.history, f.policy, f.now, 60, **kwargs)

    def test_ranked_cap_survives_and_eligible_alternative_source_is_bounded(self):
        result = self.select()
        self.assertEqual(len(result['candidates']), 60)
        self.assertTrue(all(x['notice_id'].startswith('cleaneye-') for x in result['candidates']))
        alternatives = result['official_source_alternatives']
        self.assertEqual(len(alternatives), 8)
        self.assertTrue(all(x['selection_context']['decision'] == 'eligible_for_official_review'
                            and x['selection_context']['included_in_writer_input'] is False
                            for x in alternatives))
        self.assertEqual([x['notice_id'] for x in alternatives], ['a' + str(i) for i in range(700, 708)])

    def test_fallback_cannot_reintroduce_queued_stale_unknown_or_closed_notices(self):
        f = self.fixture
        f.details['a700']['scrnprcdrMthdExpln'] = '접수일 별도 확인 필요'
        f.details['a701']['ongoingYn'] = 'N'
        f.history['posted_ids'] = ['a702']
        result = self.select(queued_entries=[{'notice_id': 'a703', 'scheduled_at': f.slot.isoformat(),
                                             'writer': {'status': 'ready'}}])
        ids = {x['notice_id'] for x in result['official_source_alternatives']}
        self.assertFalse(ids & {'a700', 'a701', 'a702', 'a703'})
        f.source['_operations']['last_success_at'] = '2026-11-04T10:00:00+09:00'
        self.assertEqual(self.select()['official_source_alternatives'], [])

    def test_full_handoff_reaches_alio_after_cleaneye_outage_without_approval(self):
        f = self.fixture
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return f.now
        empty = {'schema_version': 1, 'entries': []}
        before = deepcopy((f.source, f.details, f.history, empty))
        with patch.object(bridge, 'datetime', Clock), \
             patch.object(bridge, 'read', return_value=(empty, 'a' * 40)), \
             patch.object(bridge, 'writer_inputs', return_value=(f.policy, f.source, f.details)), \
             patch.object(bridge, 'load', return_value=f.history), \
             patch.object(bridge, 'request') as mutation, \
             patch.dict(bridge.os.environ, {'THREADS_CLAIM_TOKEN': 'synthetic-read-only-test',
                                            'GITHUB_REPOSITORY': 'synthetic/test'}):
            report = bridge.run(apply=False)
        mutation.assert_not_called()
        drafts = build_drafts(report['writer_handoff'])
        self.assertTrue(all(x['notice_id'].startswith('cleaneye-') for x in drafts['drafts']))
        calls = []
        def fetched(url):
            calls.append(url)
            if 'job.cleaneye.go.kr' in url:
                raise urllib.error.URLError('synthetic provider outage')
            return {'url': url, 'sha256': 'a' * 64}
        packet = build_packet(drafts, fetch=fetched)
        self.assertEqual(packet['checked'], 8)
        self.assertEqual(packet['attempted'], 12)
        self.assertEqual(packet['unavailable_hosts'], ['job.cleaneye.go.kr'])
        self.assertEqual(sum('job.cleaneye.go.kr' in url for url in calls), 4)
        self.assertFalse(packet['approved_for_queue'])
        self.assertFalse(packet['automatic_approval'])
        self.assertFalse(packet['meta_posted'])
        self.assertEqual(report['approved_supply_count'], 0)
        self.assertEqual(before, (f.source, f.details, f.history, empty))

    def test_unused_candidate_keeps_exact_employer_pin_fingerprints(self):
        pin = CANONICAL_REVIEW_URLS['cleaneye-80820']
        candidate = {'notice_id': 'cleaneye-80820', 'official_url':
                     'https://job.cleaneye.go.kr/user/ypCareersData.do?idx=80820',
                     'source_post_sha256': pin['source_post_sha256'],
                     'source_detail_sha256': pin['source_detail_sha256']}
        drafts = build_drafts({'automatic_approval': False, 'meta_posted': False,
                               'missing_slots': [], 'candidates': [candidate]})
        alternative = drafts['official_source_alternatives'][0]
        self.assertEqual(independently_located_notice(alternative), pin['url'])
        alternative['source_detail_sha256'] = '0' * 64
        self.assertEqual(independently_located_notice(alternative), candidate['official_url'])


if __name__ == '__main__':
    unittest.main()
