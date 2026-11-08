"""Publication-boundary failures and recovery, with zero real API mutations."""
import base64
from copy import deepcopy
import io
import json
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch

from scripts import threads_auto as publisher
from scripts.threads_http import read_response
from scripts.threads_reconcile import finalize_unsent, reconcile_accepted
from scripts.threads_remote_claim import ClaimError, GitHubClaims
from tests import test_threads_writer_queue as queue_fixtures


class MasterPipelineTests(unittest.TestCase):
    def setUp(self):
        self.fixture = queue_fixtures.WriterQueueTests()
        self.fixture.setUp()
        self.now = self.fixture.slot.replace(minute=5)
        self.queue = {'schema_version': 1, 'entries': [self.fixture.entry]}
        self.env = {'THREADS_SCHEDULE_CRON': '0 3 * * *', 'THREADS_MANUAL_PUBLISH': 'false',
                    'THREADS_ENABLED': 'true', 'THREADS_ACCESS_TOKEN': 'fake',
                    'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_RUN_ID': '880'}

    def prepare(self, previous_image=None):
        history = deepcopy(self.fixture.history)
        if previous_image is not None:
            history['records'].append({'job_id': 'a699', 'status': 'published',
                'threads_post_id': '123', 'image_url': previous_image,
                'scheduled_at': '2026-11-05T20:00:00+09:00',
                'reserved_date': '2026-11-05', 'text': '이전 공고'})
            self.fixture.entry['writer']['review']['repetition_check'] = 'checked'
        with patch.dict(os.environ, self.env), patch.object(publisher, 'writer_inputs',
                return_value=(self.fixture.policy, self.fixture.source, self.fixture.details)), \
                patch.object(publisher, 'load', return_value=self.queue), patch.object(publisher, 'save'):
            publisher.prepare_master(history, self.now, '880')
        return history, history['records'][-1]

    def test_alternation_uses_last_confirmed_across_days_and_reservation_is_immutable(self):
        for prior, wants_image in [(None, False), ('', True), ('https://previous/image.jpg', False)]:
            with self.subTest(prior=prior):
                history, record = self.prepare(prior)
                self.assertEqual(bool(record['image_url']), wants_image)
                self.assertEqual(record['text'], self.fixture.entry['writer']['post_text'])
                self.assertEqual(record['reply_text'], '')
                self.assertEqual(record['engagement_text'], '')
                with patch.dict(os.environ, self.env), patch.object(publisher, 'save') as save:
                    with self.assertRaisesRegex(RuntimeError, 'Unresolved prior reservation'):
                        publisher.prepare_master(history, self.now, '881')
                    save.assert_not_called()

    def test_compact_publication_uses_verified_facts_and_one_detail_reply(self):
        self.fixture.policy['publication_style'] = publisher.COMPACT_STYLE
        history, record = self.prepare('https://previous/image.jpg')
        self.assertFalse(record['image_url'])
        self.assertIn('🏢 예시연구원', record['text'])
        self.assertIn('👥 정규직 · 3명', record['text'])
        self.assertIn('접수 마감: 2026-11-18 17:00', record['text'])
        self.assertNotIn('2026-11-30', record['text'])
        self.assertIn('정보보안 기사 자격이 필요해요.', record['reply_text'])
        self.assertTrue(record['text'].endswith(queue_fixtures.CTA))
        self.assertNotIn(queue_fixtures.CTA, record['reply_text'])
        self.assertEqual(record['engagement_text'], '')
        with patch.object(publisher, 'writer_inputs',
                          return_value=(self.fixture.policy, self.fixture.source, self.fixture.details)):
            publisher.validate_master_before_send(record, history, self.now)
            record['reply_text'] += ' 확인되지 않은 문장'
            with self.assertRaisesRegex(RuntimeError, 'Reserved text, detail reply or format changed'):
                publisher.validate_master_before_send(record, history, self.now)

    def test_compact_reply_is_attempted_once_and_verified_with_its_parent(self):
        self.fixture.policy['publication_style'] = publisher.COMPACT_STYLE
        history, record = self.prepare()
        parent = {'id': '12345', 'text': record['text']}
        reply = {'id': '12346', 'text': record['reply_text'], 'is_reply': True,
                 'root_post': {'id': '12345'}, 'replied_to': {'id': '12345'}}
        snapshots = []
        with patch.dict(os.environ, self.env), patch.object(publisher, 'validate_master_before_send'), \
                patch.object(publisher, 'verify_account', return_value='1'), \
                patch.object(publisher, 'save', side_effect=lambda state: snapshots.append(deepcopy(state))), \
                patch('scripts.threads_remote_claim.GitHubClaims'), patch.object(publisher.time, 'sleep'), \
                patch.object(publisher, 'api', return_value=parent), \
                patch.object(publisher, 'create_media', side_effect=['12345', '12346']) as media:
            publisher.publish_post(record, history)
            publisher.publish_post(record, history)
            self.assertEqual(media.call_count, 2)
            self.assertEqual(media.call_args.args[1]['reply_to_id'], '12345')
        self.assertTrue(any(s['records'][-1].get('reply_status') == 'attempted' for s in snapshots))
        self.assertEqual(record['reply_status'], 'confirmed')
        with patch.object(publisher, 'api', side_effect=[parent, reply]):
            self.assertEqual(publisher.verify_published_record(record, 'fake'), [parent, reply])
        with patch.object(publisher, 'api', side_effect=[parent, {**reply, 'root_post': {'id': '9'}}]):
            with self.assertRaisesRegex(RuntimeError, 'parent/root mismatch'):
                publisher.verify_published_record(record, 'fake')

    def test_ambiguous_compact_reply_is_not_replayed(self):
        self.fixture.policy['publication_style'] = publisher.COMPACT_STYLE
        history, record = self.prepare()
        with patch.dict(os.environ, self.env), patch.object(publisher, 'validate_master_before_send'), \
                patch.object(publisher, 'verify_account', return_value='1'), patch.object(publisher, 'save'), \
                patch('scripts.threads_remote_claim.GitHubClaims'), patch.object(publisher.time, 'sleep'), \
                patch.object(publisher, 'api', return_value={'id': '12345'}), \
                patch.object(publisher, 'create_media', side_effect=['12345', RuntimeError('timeout')]) as media:
            publisher.publish_post(record, history)
            publisher.publish_post(record, history)
            self.assertEqual(media.call_count, 2)
        self.assertEqual(record['status'], 'published')
        self.assertEqual(record['reply_status'], 'needs_review')

    def test_compact_accepted_recovery_checks_main_without_sending_reply(self):
        self.fixture.policy['publication_style'] = publisher.COMPACT_STYLE
        history, record = self.prepare()
        remote = Mock()
        remote.read.return_value = {'slot': record['scheduled_at'], 'run_id': '880',
                                   'state': 'accepted', 'post_id': '12345'}
        with patch.object(publisher, 'api', return_value={'id': '12345', 'text': record['text']}) as api, \
                patch.object(publisher, 'create_media') as send:
            results = reconcile_accepted(history, remote, 'fake')
            self.assertEqual(results[0]['status'], 'verified_recovered')
            self.assertEqual(record['reply_status'], 'needs_review')
            api.assert_called_once()
            send.assert_not_called()

    def test_missing_required_image_never_falls_back_or_claims_slot(self):
        history, record = self.prepare('')
        with patch.dict(os.environ, self.env), \
                patch.object(publisher, 'validate_master_before_send'), \
                patch.object(publisher, 'verify_account', return_value='1'), \
                patch.object(publisher, 'image_ready', return_value=False), \
                patch('scripts.threads_remote_claim.GitHubClaims') as remote, \
                patch.object(publisher, 'create_media') as media:
            with self.assertRaisesRegex(RuntimeError, 'Required image unavailable'):
                publisher.publish_post(record, history)
            remote.assert_not_called()
            media.assert_not_called()
        self.assertTrue(record['image_url'])
        self.assertTrue(finalize_unsent(history, '880'))
        self.assertTrue(record['safe_no_send'])
        self.assertEqual(record['failure_stage'], 'before_remote_claim')

    def test_ambiguous_claim_is_marked_before_mutation_and_never_released(self):
        history, record = self.prepare()
        snapshots = []
        def ambiguous(*args):
            self.assertEqual(snapshots[-1]['records'][-1]['request_status'], 'claim_attempted')
            raise ClaimError('ambiguous')
        with patch.dict(os.environ, self.env), patch.object(publisher, 'validate_master_before_send'), \
                patch.object(publisher, 'verify_account', return_value='1'), \
                patch.object(publisher, 'save', side_effect=lambda state: snapshots.append(deepcopy(state))), \
                patch('scripts.threads_remote_claim.GitHubClaims') as remote, \
                patch.object(publisher, 'create_media') as media:
            remote.return_value.begin.side_effect = ambiguous
            with self.assertRaises(ClaimError):
                publisher.publish_post(record, history)
            media.assert_not_called()
        self.assertFalse(finalize_unsent(history, '880'))
        self.assertEqual(record['status'], 'pending')

    def test_master_publishes_exactly_one_object_and_verifies_only_it(self):
        history, record = self.prepare()
        with patch.dict(os.environ, self.env), patch.object(publisher, 'validate_master_before_send'), \
                patch.object(publisher, 'verify_account', return_value='1'), \
                patch.object(publisher, 'save'), patch('scripts.threads_remote_claim.GitHubClaims'), \
                patch.object(publisher, 'create_media', return_value='12345') as media:
            publisher.publish_post(record, history)
            publisher.publish_post(record, history)
            self.assertEqual(media.call_count, 1)
        with patch.object(publisher, 'api', return_value={'id': '12345', 'text': record['text']}) as api:
            self.assertEqual(len(publisher.verify_published_record(record, 'fake')), 1)
            self.assertEqual(api.call_args.args[0], 'GET')
        self.assertFalse(finalize_unsent(history, '880'))

    def test_returned_id_survives_failed_remote_receipt_without_post_retry(self):
        history, record = self.prepare()
        with patch.dict(os.environ, self.env), patch.object(publisher, 'validate_master_before_send'), \
                patch.object(publisher, 'verify_account', return_value='1'), patch.object(publisher, 'save'), \
                patch('scripts.threads_remote_claim.GitHubClaims') as remote, \
                patch.object(publisher, 'create_media', return_value='12345') as media:
            remote.return_value.accept.side_effect = ClaimError('uncertain')
            with self.assertRaises(ClaimError):
                publisher.publish_post(record, history)
            self.assertEqual(record['api_returned_post_id'], '12345')
            with self.assertRaisesRegex(RuntimeError, 'Ambiguous request'):
                publisher.publish_post(record, history)
            self.assertEqual(media.call_count, 1)
        self.assertFalse(finalize_unsent(history, '880'))

    def test_accepted_recovery_requires_live_text_and_never_calls_publish(self):
        history, record = self.prepare()
        remote = Mock()
        remote.read.return_value = {'slot': record['scheduled_at'], 'run_id': '880',
                                   'state': 'accepted', 'post_id': '12345'}
        original = deepcopy(history)
        with patch.object(publisher, 'create_media') as send:
            results = reconcile_accepted(history, remote, 'fake',
                verifier=Mock(side_effect=RuntimeError('text mismatch')))
            self.assertEqual(results[0]['status'], 'hold')
            self.assertEqual(history, original)
            results = reconcile_accepted(history, remote, 'fake',
                verifier=Mock(return_value=[{'id': '12345', 'text': record['text'], 'permalink': 'verified'}]))
            self.assertEqual(results[0]['status'], 'verified_recovered')
            send.assert_not_called()
        self.assertEqual(record['threads_post_id'], '12345')
        self.assertEqual(history['posted_ids'], ['a700'])


class ReadRetryTests(unittest.TestCase):
    def error(self, code, headers=None):
        return urllib.error.HTTPError('https://example.invalid', code, 'error', headers or {}, io.BytesIO())

    def test_transient_reads_retry_and_honor_retry_after(self):
        marker = object()
        opener = Mock(side_effect=[self.error(503), self.error(429, {'Retry-After': '7'}), marker])
        sleeper = Mock()
        self.assertIs(read_response(urllib.request.Request('https://example.invalid'),
                      opener=opener, sleeper=sleeper), marker)
        self.assertEqual([c.args[0] for c in sleeper.call_args_list], [2, 7])

    def test_permissions_long_rate_limit_and_mutations_are_never_retried(self):
        for error in (self.error(401), self.error(403), self.error(429, {'Retry-After': '90'})):
            opener, sleeper = Mock(side_effect=error), Mock()
            with self.assertRaises(urllib.error.HTTPError):
                read_response(urllib.request.Request('https://example.invalid'), opener=opener, sleeper=sleeper)
            self.assertEqual(opener.call_count, 1)
            sleeper.assert_not_called()
        with self.assertRaises(ValueError):
            read_response(urllib.request.Request('https://example.invalid', method='POST'), opener=Mock())

    def test_accepted_receipt_response_loss_is_reconciled_with_exact_readback(self):
        claim = GitHubClaims('owner/repo', 'state', 'fake')
        data = {'slot': '2026-11-06T12:00:00+09:00', 'run_id': '88', 'state': 'accepted', 'post_id': '123'}
        result = {'content': base64.b64encode(json.dumps(data).encode()).decode()}
        with patch.object(claim, '_request', side_effect=[ClaimError('lost response'), result]) as request:
            claim.accept(data['slot'], '88', 'original-sha', '123')
            self.assertEqual([call.args[0] for call in request.call_args_list], ['PUT', 'GET'])


if __name__ == '__main__':
    unittest.main()
