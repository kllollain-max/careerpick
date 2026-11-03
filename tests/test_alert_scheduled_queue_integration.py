"""Exercise the production scheduled entrypoint; every external service is fake."""
import copy
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import ExitStack, redirect_stdout, nullcontext
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from scripts import send_all_opted_in_bounded as worker
from scripts import private_delivery_store as ledger_store
from scripts import onesignal_guarded_transport as transport
from scripts import onesignal_safe_retry as retry
from scripts.alert_delivery_ledger import delivery_key
from test_alert_all_opted_in_bounded import FakePrivateQueue


class Crash(BaseException):
    pass


class Harness:
    def __init__(self, n=4, jobs=1, *, real_circuit=False):
        self.real_circuit = real_circuit
        self.ids = ['synthetic-%04d' % i for i in range(n)]
        self.jobs = [dict(id='a%d' % j, title='Recruitment', region='r%d' % j,
                          due='2099-12-01', emp='Permanent') for j in range(jobs)]
        self.subs = {sid: dict(subscription_id=sid, opted_in=True, tags={
            'cp_optin': 'yes', 'cp_profile': json.dumps(dict(
                v=4, region=['r%d' % (i % jobs)], employment=[], education=[], category=[], keywords=''))})
                     for i, sid in enumerate(self.ids)}
        self.queue = FakePrivateQueue()
        self.ledger = {'delivered': [], 'pending': []}
        self.ledger_version = 1
        self.ledger_lock = threading.Lock()
        self.backlog = []
        self.cursor = {'version': 1, 'next_index': 0, 'export_hash': ''}
        self.cursor_version = 0
        self.sent = []
        self.lookup_ids = []
        self.stack = ExitStack()
        self.temp = tempfile.TemporaryDirectory()
        self.report = Path(self.temp.name) / 'report.json'
        self.write_report(self.jobs)
        self.sender = self.send

    def write_report(self, jobs):
        self.report.write_text(json.dumps(dict(dry_run=True, initial_run=False,
            checked_at=datetime.now(worker.KST).isoformat(), new_jobs=jobs)))

    def request(self, url, token, method='GET', payload=None):
        # Run the REAL private ledger reader/reserver/finalizer on fake GitHub CAS.
        import base64
        with self.ledger_lock:
            if method == 'GET':
                return dict(content=base64.b64encode(json.dumps(self.ledger).encode()).decode(),
                            sha=str(self.ledger_version))
            if payload.get('sha') != str(self.ledger_version):
                raise HTTPError(url, 409, 'conflict', {}, None)
            self.ledger = json.loads(base64.b64decode(payload['content']))
            self.ledger_version += 1
            return dict(content=dict(sha=str(self.ledger_version)))

    def lookup(self, sid):
        self.lookup_ids.append(sid)
        return copy.deepcopy(self.subs.get(sid))

    def send(self, job, sid, **kwargs):
        key = delivery_key(job['id'], sid)
        data, _ = self.queue.read()
        assert data['tasks'][key]['state'] == 'reserved'
        assert key in self.ledger['pending']
        if key in self.sent:
            raise AssertionError('Duplicate provider request')
        self.sent.append(key)
        return dict(sent=True, notification_id='msg-' + key[:16], reason='api_accepted')

    def save_cursor(self, index, export_hash, sha):
        if sha != str(self.cursor_version):
            raise RuntimeError('Cursor CAS conflict')
        self.cursor = dict(version=1, next_index=index, export_hash=export_hash)
        self.cursor_version += 1

    def __enter__(self):
        if not self.real_circuit:
            guard = MagicMock()
            self.stack.enter_context(patch.object(worker.circuit, "session", side_effect=lambda: nullcontext(guard)))
            self.stack.enter_context(patch.object(worker.circuit, "current", return_value=guard))
        bindings = [
            (worker, 'verify_current_job', lambda *args: {'allowed': True}),
            (worker.queue, 'read_queue', self.queue.read),
            (worker.queue, 'write_queue', self.queue.write),
            (ledger_store, '_config', lambda: ('private/fixture', 'fake')),
            (ledger_store, '_request', self.request),
            (worker, 'read_backlog', lambda: (copy.deepcopy(self.backlog), 'backlog-sha')),
            (worker, 'save_backlog', lambda data, sha: setattr(self, 'backlog', copy.deepcopy(data))),
            (worker, 'request_export', lambda *args: 'fake-export'),
            (worker, 'read_export_ids', lambda url: list(self.ids)),
            (worker, 'read_cursor', lambda: (dict(self.cursor), str(self.cursor_version))),
            (worker, 'save_cursor', self.save_cursor),
            (worker, 'lookup', self.lookup),
            (worker, 'send', lambda *args, **kwargs: self.sender(*args, **kwargs)),
        ]
        for obj, name, fn in bindings:
            self.stack.enter_context(patch.object(obj, name, side_effect=fn))
        # A missed stub must fail; these tests cannot contact GitHub or OneSignal.
        self.stack.enter_context(patch('socket.create_connection', side_effect=AssertionError('Live network forbidden')))
        self.stack.enter_context(patch.dict(os.environ, dict(CP_ENABLE_ALL_OPTED_IN_ROLLOUT='1',
            CP_ENABLE_LIVE_PUSH='1', CP_ALERT_REPORT=str(self.report),
            CP_ONESIGNAL_APP_ID='fake-app', CP_ONESIGNAL_REST_API_KEY='fake-key'), clear=True))
        return self

    def __exit__(self, *args):
        self.stack.close()
        self.temp.cleanup()

    def run(self):
        self.lookup_ids.clear()
        with redirect_stdout(io.StringIO()) as output:
            worker.main()
        # Includes <=3 immediate consent rechecks of already-scanned subscribers.
        assert len(set(self.lookup_ids)) <= 100
        return output.getvalue()


class ScheduledQueueIntegrationTests(unittest.TestCase):
    def test_66000_candidates_full_eligible_drain_with_restart_and_history(self):
        with Harness(1000, 66) as h:
            candidates = [(job['id'], sid) for sid in h.ids for job in h.jobs]
            self.assertEqual(len(candidates), 66000)
            # Independent expected set: exactly one matching region per subscriber.
            expected = {delivery_key('a%d' % (i % 66), sid) for i, sid in enumerate(h.ids)}
            previous = sorted(expected)[:10]
            unresolved = sorted(expected)[10]
            h.ledger = dict(delivered=previous, pending=[unresolved])
            expected_new = expected - set(previous) - {unresolved}
            rounds, max_batch = 0, 0
            while True:
                before = len(h.sent)
                h.run()
                max_batch = max(max_batch, len(h.sent) - before)
                self.assertLessEqual(len(h.sent) - before, 3)
                rounds += 1
                if rounds == 5:
                    # New process snapshots and reset cursor cannot erase the queue.
                    h.queue.data = json.loads(json.dumps(h.queue.data))
                    h.cursor = dict(version=1, next_index=0, export_hash='')
                    h.write_report([])  # all jobs now come from durable backlog
                if h.cursor['next_index'] == 0 and set(h.sent) == expected_new:
                    break
                self.assertLess(rounds, 400)
            state, _ = h.queue.read()
            self.assertEqual(set(h.sent), expected_new)
            self.assertEqual(len(h.sent), len(set(h.sent)))
            self.assertEqual(worker.queue.counts(state), dict(
                total=990, accepted=989, uncertain=1, pending=0, reserved=0, failed=0))
            self.assertTrue(all(v['message_id'] for v in state['tasks'].values() if v['state'] == 'accepted'))
            self.assertEqual(set(h.ledger['pending']), {unresolved})
            print('INTEGRATION: candidates=66000 eligible=1000 historical=10 unresolved=1 accepted=989 '
                  'rounds=%d max_batch=%d duplicates=0 missing=0' % (rounds, max_batch))

    def test_new_subscriber_and_job_preserve_existing_queue(self):
        with Harness(4, 1) as h:
            h.run()
            old = set(h.queue.data['tasks'])
            h.ids.append('new-subscriber')
            h.subs['new-subscriber'] = dict(h.subs[h.ids[0]], subscription_id='new-subscriber')
            h.jobs.append(dict(h.jobs[0], id='a100'))
            h.write_report(h.jobs)
            for _ in range(4):
                h.run()
            self.assertTrue(old <= set(h.queue.data['tasks']))
            self.assertEqual(len(h.sent), 10)
            self.assertEqual(len(h.sent), len(set(h.sent)))

    def test_crash_after_api_acceptance_quarantines_and_other_tasks_continue(self):
        with Harness() as h:
            def crash(*args, **kwargs):
                h.send(*args, **kwargs)
                raise Crash()
            h.sender = crash
            with self.assertRaises(Crash):
                h.run()
            self.assertEqual(worker.queue.counts(h.queue.data)['reserved'], 1)
            h.sender = h.send
            h.run()
            self.assertEqual(len(h.sent), 4)
            self.assertEqual(worker.queue.counts(h.queue.data)['uncertain'], 1)
            self.assertEqual(worker.queue.counts(h.queue.data)['accepted'], 3)

    def test_preclaim_storage_failure_never_sends(self):
        with Harness() as h:
            def fail(data):
                if worker.queue.counts(data)['reserved']:
                    raise OSError('storage offline')
            h.queue.fail_write = fail
            with self.assertRaises(OSError):
                h.run()
            self.assertEqual(h.sent, [])
            h.queue.fail_write = None
            h.run()
            self.assertEqual(len(h.sent), 3)

    def test_response_saved_but_ack_lost_never_replays(self):
        with Harness() as h:
            original = h.queue.write
            lost = [False]
            def write(data, sha):
                result = original(data, sha)
                if worker.queue.counts(data)['accepted'] and not lost[0]:
                    lost[0] = True
                    raise OSError('response lost')
                return result
            with patch.object(worker.queue, 'write_queue', side_effect=write):
                with self.assertRaisesRegex(RuntimeError, 'outcome persistence'):
                    h.run()
            h.run()
            self.assertEqual(len(h.sent), 4)
            self.assertEqual(worker.queue.counts(h.queue.data)['accepted'], 4)

    def test_api_success_then_all_outcome_writes_fail(self):
        with Harness() as h:
            def fail(data):
                states = worker.queue.counts(data)
                if states['accepted'] or states['uncertain']:
                    raise OSError('storage offline')
            h.queue.fail_write = fail
            with self.assertRaisesRegex(RuntimeError, 'outcome persistence'):
                h.run()
            h.queue.fail_write = None
            h.run()
            self.assertEqual(len(h.sent), 4)
            self.assertEqual(worker.queue.counts(h.queue.data)['uncertain'], 1)

    def test_concurrent_claim_cas_has_one_owner(self):
        with Harness(1, 1) as h:
            pairs = [(h.jobs[0], h.subs[h.ids[0]])]
            h.queue.data = worker.queue.enqueue(worker.queue.empty_queue(), pairs, h.ledger)
            key = next(iter(h.queue.data['tasks']))
            barrier = threading.Barrier(2)
            local = threading.local()
            def simultaneous_read():
                result = h.queue.read()
                if not getattr(local, 'read_once', False):
                    local.read_once = True
                    barrier.wait(timeout=5)
                return result
            outcomes = []
            def contender(owner):
                if worker.queue.claim(key, owner):
                    # Actual legacy reservation remains part of the send boundary.
                    if worker.reserve_private_delivery(h.jobs[0]['id'], h.ids[0]):
                        h.send(h.jobs[0], h.ids[0])
                    outcomes.append(owner)
            with patch.object(worker.queue, 'read_queue', side_effect=simultaneous_read):
                threads = [threading.Thread(target=contender, args=(str(i),)) for i in range(2)]
                for thread in threads: thread.start()
                for thread in threads: thread.join(timeout=10)
                self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(len(h.sent), 1)

    def test_two_full_workers_overlap_while_request_inflight(self):
        with Harness(1, 1) as h:
            entered, release = threading.Event(), threading.Event()
            errors = []
            def blocked_send(*args, **kwargs):
                result = h.send(*args, **kwargs)
                entered.set()
                self.assertTrue(release.wait(timeout=5))
                return result
            h.sender = blocked_send
            def first():
                try:
                    worker.process_window(h.jobs, list(h.subs.values()), copy.deepcopy(h.ledger),
                                          datetime.now(worker.KST), current_ids=h.ids)
                except Exception as error:
                    errors.append(error)
            with redirect_stdout(io.StringIO()):
                thread = threading.Thread(target=first)
                thread.start()
                self.assertTrue(entered.wait(timeout=5))
                worker.process_window(h.jobs, list(h.subs.values()), copy.deepcopy(h.ledger),
                                      datetime.now(worker.KST), current_ids=h.ids)
                release.set()
                thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(h.sent), 1)
            self.assertEqual(worker.queue.counts(h.queue.data)['accepted'], 1)

    def test_legacy_reservation_race_blocks_request(self):
        with Harness(1, 1) as h:
            original = worker.reserve_private_delivery
            def other_sender(job, sid):
                self.assertTrue(original(job, sid))
                return original(job, sid)
            with patch.object(worker, 'reserve_private_delivery', side_effect=other_sender):
                h.run()
            self.assertEqual(h.sent, [])
            self.assertEqual(worker.queue.counts(h.queue.data)['uncertain'], 1)

    def test_optout_after_enqueue_records_failed(self):
        with Harness(1, 1) as h:
            original = h.lookup
            def lookup(sid):
                result = original(sid)
                if len(h.lookup_ids) > 1:
                    result['opted_in'] = False
                return result
            with patch.object(worker, 'lookup', side_effect=lookup):
                h.run()
            self.assertEqual(h.sent, [])
            self.assertEqual(worker.queue.counts(h.queue.data)['failed'], 1)

    def test_real_transport_retry_and_outcomes_are_persisted(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"id":"fake-provider-id","recipients":1}'
        for error, final, calls in [(429, 'accepted', 2), (503, 'uncertain', 1),
                                     (408, 'uncertain', 1), (400, 'failed', 1),
                                     ('network', 'uncertain', 1)]:
            with self.subTest(error=error), Harness(1, 1) as h:
                h.sender = transport.send
                attempts = []
                def open_fake(request, timeout):
                    attempts.append(1)
                    if len(attempts) == 1:
                        if error == 'network': raise URLError('response lost')
                        raise HTTPError('https://fake.invalid', error, 'fake', {'Retry-After': '0'}, io.BytesIO(b'{}'))
                    return Response()
                original_post = retry.post
                with patch.object(transport, 'urlopen', side_effect=open_fake), patch.object(
                        retry, 'post', side_effect=lambda request, **kw: original_post(request, sleeper=lambda _: None, **kw)):
                    h.run()
                self.assertEqual(len(attempts), calls)
                self.assertEqual(worker.queue.counts(h.queue.data)[final], 1)
                if final == 'accepted':
                    self.assertEqual(next(iter(h.queue.data['tasks'].values()))['message_id'], 'fake-provider-id')
                h.run()
                self.assertEqual(len(attempts), calls)

    def test_workflow_calls_integrated_entrypoint_and_ci_discovers_suite(self):
        root = Path(__file__).resolve().parents[1]
        scheduled = (root / '.github/workflows/targeted-push.yml').read_text()
        self.assertIn('python -m scripts.run_targeted_push', scheduled)
        self.assertIn('workflow_run:', scheduled)
        self.assertNotIn('cron:', scheduled)
        self.assertIn("vars.CP_ENABLE_ALL_OPTED_IN_ROLLOUT == '1'", scheduled)
        ci = (root / '.github/workflows/targeted-push-check.yml').read_text()
        self.assertIn('python tests/run_alert_recovery.py', ci)

class QueueStorageBoundaryTests(unittest.TestCase):
    def test_66000_task_snapshot_reads_blob_when_contents_are_not_inline(self):
        import base64
        q = worker.queue
        pairs = (({'id': 'a%d' % j}, {'subscription_id': 'synthetic-%d' % i})
                 for i in range(1000) for j in range(66))
        state = q.enqueue(q.empty_queue(), pairs, {'delivered': [], 'pending': []})
        encoded = base64.b64encode(json.dumps(state).encode()).decode()
        self.assertGreater(len(encoded), 2_000_000)
        # Contents API omits data above 1MB; retrieve same SHA via Git Blobs API.
        with patch.object(q, '_config', return_value=('private/fixture', 'fake')), patch.object(
                q, '_request', side_effect=[dict(sha='blob-sha', content='', encoding='none'),
                                          dict(content=encoded, encoding='base64')]) as request:
            restored, sha = q.read_queue()
        self.assertEqual(restored, state)
        self.assertEqual(sha, 'blob-sha')
        self.assertTrue(request.call_args.args[0].endswith('/git/blobs/blob-sha'))
        self.assertEqual(q.counts(restored)['pending'], 66000)

    def test_long_retry_after_stops_without_premature_replay(self):
        attempts = []
        def opener(request, timeout):
            attempts.append(1)
            raise HTTPError('https://fake.invalid', 429, 'rate limit', {'Retry-After': '120'}, None)
        with self.assertRaises(retry.RejectedRequest):
            retry.post(object(), opener=opener, sleeper=lambda _: self.fail('Wait budget exceeded'))
        self.assertEqual(len(attempts), 1)

class RealProcessRecoveryTests(unittest.TestCase):
    def test_exit_immediately_after_provider_response_then_restart_entrypoint(self):
        import subprocess
        import sys
        script = r'''
import json, os, sys
from pathlib import Path
from test_alert_scheduled_queue_integration import Harness
root = Path(sys.argv[1])
with Harness() as h:
    snapshot = root / 'backend.json'
    if snapshot.exists():
        value = json.loads(snapshot.read_text())
        h.queue.data = value['queue']
        h.queue.version = value['queue_version']
        h.ledger = value['ledger']
        h.ledger_version = value['ledger_version']
        h.sent = value['requests']
    def persist():
        value = dict(queue=h.queue.data, queue_version=h.queue.version,
                     ledger=h.ledger, ledger_version=h.ledger_version, requests=h.sent)
        snapshot.write_text(json.dumps(value))
    original_write, original_request = h.queue.write, h.request
    def write(*args):
        result = original_write(*args)
        persist()
        return result
    def request(*args, **kwargs):
        result = original_request(*args, **kwargs)
        persist()
        return result
    # Patch side effects dynamically because Harness bindings were made at entry.
    from unittest.mock import patch, MagicMock
    from scripts import private_delivery_store as store
    from scripts import send_all_opted_in_bounded as worker
    with patch.object(worker.queue, 'write_queue', side_effect=write), patch.object(store, '_request', side_effect=request):
        if sys.argv[2] == 'crash':
            def crash(*args, **kwargs):
                result = h.send(*args, **kwargs)
                persist()
                os._exit(71)
            h.sender = crash
        h.run()
        persist()
'''
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent) + os.pathsep + str(Path.cwd()))
            first = subprocess.run([sys.executable, '-c', script, folder, 'crash'], env=env,
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(first.returncode, 71, first.stderr)
            second = subprocess.run([sys.executable, '-c', script, folder, 'resume'], env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(second.returncode, 0, second.stderr)
            state = json.loads((Path(folder) / 'backend.json').read_text())
            self.assertEqual(len(state['requests']), 4)
            self.assertEqual(len(set(state['requests'])), 4)
            self.assertEqual(worker.queue.counts(state['queue'])['uncertain'], 1)
            self.assertEqual(worker.queue.counts(state['queue'])['accepted'], 3)
