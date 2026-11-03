"""Only new regular-path gaps and accepted test replay prevention."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest.mock import patch
from scripts import send_all_opted_in_bounded as worker
from scripts import push_official_preflight as official
from scripts.alert_candidate_backlog import reconcile
from scripts.alert_delivery_ledger import delivery_key
from scripts.verify_real_job_backlog import verify
from test_alert_scheduled_queue_integration import Harness


def page(title='Recruitment', state='진행중', agency='Agency', end='99.12.01'):
    return (f'<div class="tit">{title}</div><span class="cate01">{state}</span>'
            f'<table><tr><th>기관명</th><td>{agency}</td></tr>'
            f'<tr><th>공고기간</th><td>26.10.01 ~ {end}</td></tr></table>')


class RegularReadinessTests(unittest.TestCase):
    def test_official_open_cancelled_closed_unknown_and_changed(self):
        job = dict(id='a1', title='Recruitment', org='Agency', due='2099-12-01')
        now = datetime.now(worker.KST)
        cases = [(page(), True, True), (page(state='마감'), False, True),
                 (page(title='공고 취소 안내'), False, True), ('login page', False, False),
                 (page(end='99.12.02'), False, False), (page(agency='Other'), False, False)]
        for source, allowed, definitive in cases:
            with self.subTest(source=source):
                result = official.verify(job, now, fetcher=lambda _: source)
                self.assertEqual(result['allowed'], allowed)
                self.assertEqual(result['definitive'], definitive)
        result = official.verify(job, now, fetcher=lambda _: (_ for _ in ()).throw(TimeoutError()))
        self.assertFalse(result['definitive'])
        self.assertEqual(result['reason'], 'official_unverified')

    def test_current_cancel_flag_and_expiry_block_without_fetching(self):
        for job in [dict(id='a1', title='Recruitment', due='2099-12-01', cancelled=True),
                    dict(id='a1', title='Recruitment', due='2020-01-01')]:
            result = official.verify(job, datetime.now(worker.KST), fetcher=lambda _: self.fail('must not fetch'))
            self.assertFalse(result['allowed'])
            self.assertTrue(result['definitive'])

    def test_official_cancellation_at_send_boundary_blocks_api(self):
        with Harness(1, 1) as h, patch.object(worker, 'verify_current_job', return_value={
                'allowed': False, 'definitive': True, 'reason': 'official_cancelled_or_closed'}):
            h.run()
            self.assertEqual(h.sent, [])
            self.assertEqual(h.ledger['pending'], [])
            self.assertEqual(worker.queue.counts(h.queue.data)['failed'], 1)

    def test_unknown_official_result_keeps_pending_for_recovery(self):
        with Harness(1, 1) as h:
            with patch.object(worker, 'verify_current_job', return_value={
                    'allowed': False, 'definitive': False, 'reason': 'official_unverified'}):
                h.run()
            self.assertEqual(h.sent, [])
            self.assertEqual(h.ledger['pending'], [])
            self.assertEqual(worker.queue.counts(h.queue.data)['pending'], 1)
            h.run()
            self.assertEqual(len(h.sent), 1)

    def test_accepted_test_is_never_replayed_by_regular_main(self):
        with Harness(1, 1) as h:
            key = delivery_key(h.jobs[0]['id'], h.ids[0])
            h.queue.data = worker.queue.enqueue(worker.queue.empty_queue(), [(h.jobs[0], h.subs[h.ids[0]])], h.ledger)
            h.queue.data = worker.queue.transition(h.queue.data, key, 'reserved')
            h.queue.data = worker.queue.transition(h.queue.data, key, 'accepted', message_id='recorded-test-message')
            old_pending = delivery_key('a777', 'legacy')
            h.ledger = dict(delivered=[key], pending=[old_pending])
            before = copy.deepcopy(h.queue.data)
            h.run()
            self.assertEqual(h.sent, [])
            self.assertEqual(h.queue.data, before)
            self.assertEqual(h.ledger['pending'], [old_pending])

    def test_old_open_backlog_is_retained_only_for_durable_unfinished_tasks(self):
        now = datetime.now(worker.KST)
        entry = dict(first_seen=(now-timedelta(days=8)).isoformat(),
                     job=dict(id='a1', title='Recruitment', due='2099-12-01'))
        self.assertEqual(reconcile([entry], [], now=now), [])
        self.assertEqual(len(reconcile([entry], [], now=now, retain_job_ids={'a1'})), 1)
        closed = copy.deepcopy(entry)
        closed['job']['due'] = '2020-01-01'
        self.assertEqual(reconcile([closed], [], now=now, retain_job_ids={'a1'}), [])
        data = [entry]
        durable = worker.queue.enqueue(worker.queue.empty_queue(), [(entry['job'], {'subscription_id':'fake'})], {'delivered':[]})
        result = verify(dict(dry_run=True, initial_run=False, checked_at=now.isoformat(), new_jobs=[]),
                        reader=lambda:(copy.deepcopy(data),'sha'), writer=lambda jobs, sha:data.__setitem__(slice(None),jobs),
                        queue_reader=lambda:(durable,'q'))
        self.assertEqual(result['saved_records'], 1)
        self.assertEqual(result['next_run_retained'], 1)

    def test_new_job_and_d1_deduplication_namespaces_are_distinct(self):
        normal = delivery_key('a1', 'fake', 'new_job')
        deadline = delivery_key('a1', 'fake', 'deadline_d1:2099-12-01')
        self.assertNotEqual(normal, deadline)
        self.assertEqual(deadline, delivery_key('a1', 'fake', 'deadline_d1:2099-12-01'))
