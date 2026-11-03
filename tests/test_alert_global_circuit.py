"""Production worker + real safety session on fake CAS storage. No network."""
import copy
import os
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from scripts import private_push_circuit_breaker as circuit
from scripts import send_all_opted_in_bounded as worker
from scripts.onesignal_safe_retry import RejectedRequest
from test_alert_scheduled_queue_integration import Harness


class ControlStore:
    def __init__(self):
        self.data = dict(version=1, state='ready', failures=0, reason='fixture_reviewed')
        self.sha = 1
        self.lock = threading.Lock()
        self.fail = False

    def read(self):
        with self.lock:
            if self.fail:
                raise OSError('fake storage offline')
            return copy.deepcopy(self.data), str(self.sha)

    def write(self, data, sha):
        with self.lock:
            if self.fail:
                raise OSError('fake storage offline')
            if sha != str(self.sha):
                raise circuit.Blocked('CAS conflict')
            self.data = copy.deepcopy(data)
            self.sha += 1
            return str(self.sha)


class GlobalCircuitTests(unittest.TestCase):
    def setUp(self):
        self.control = ControlStore()
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(circuit, 'read', side_effect=self.control.read))
        self.stack.enter_context(patch.object(circuit, 'write', side_effect=self.control.write))
        self.addCleanup(self.stack.close)

    def test_two_network_failures_block_third_and_restart(self):
        with Harness(4, 1, real_circuit=True) as h:
            calls = []
            def timeout(*args, **kwargs):
                calls.append(1)
                raise TimeoutError()
            h.sender = timeout
            with self.assertRaises(circuit.Blocked): h.run()
            self.assertEqual(len(calls), 2)
            self.assertEqual(self.control.data['state'], 'blocked')
            self.assertEqual(worker.queue.counts(h.queue.data)['uncertain'], 2)
            before = copy.deepcopy(h.ledger)
            with self.assertRaises(circuit.Blocked): h.run()
            self.assertEqual(h.ledger, before)
            self.assertEqual(len(calls), 2)

    def test_failure_count_survives_clean_run_boundary(self):
        with Harness(1, 1, real_circuit=True) as h:
            h.sender = lambda *a, **k: (_ for _ in ()).throw(TimeoutError())
            h.run()
            self.assertEqual(self.control.data['failures'], 1)
            # A new task, without clearing its predecessor or its reservation.
            h.jobs[0]['id'] = 'a999'
            h.write_report(h.jobs)
            with self.assertRaises(circuit.Blocked): h.run()
            self.assertEqual(self.control.data['failures'], 2)

    def test_auth_failure_immediately_stops_other_targets(self):
        for reason in ('http_401', 'http_403'):
            self.control.data = dict(version=1, state='ready', failures=0)
            with Harness(4, 1, real_circuit=True) as h:
                calls = []
                def rejected(*a, **k):
                    calls.append(1)
                    raise RejectedRequest('private details withheld', reason)
                h.sender = rejected
                with self.assertRaises(circuit.Blocked): h.run()
                self.assertEqual(len(calls), 1)
                self.assertEqual(self.control.data['state'], 'blocked')

    def test_queue_write_failure_blocks_without_provider_request(self):
        with Harness(3, 1, real_circuit=True) as h:
            h.queue.fail_write = lambda _: (_ for _ in ()).throw(OSError())
            with self.assertRaises(OSError): h.run()
            self.assertEqual(h.sent, [])
            self.assertEqual(self.control.data['state'], 'blocked')
            h.queue.fail_write = None
            with self.assertRaises(circuit.Blocked): h.run()

    def test_storage_outage_after_arming_remains_sticky_on_restart(self):
        with Harness(1, 1, real_circuit=True) as h:
            def outage(_):
                self.control.fail = True
                raise OSError()
            h.queue.fail_write = outage
            with self.assertRaises(OSError): h.run()
            self.control.fail = False
            self.assertEqual(self.control.data['state'], 'armed')
            with self.assertRaises(circuit.Blocked): h.run()
            self.assertEqual(h.sent, [])

    def test_post_success_queue_save_failure_preserves_message_no_resend(self):
        with Harness(2, 1, real_circuit=True) as h:
            original = h.send
            def accepted(*a, **k):
                response = original(*a, **k)
                h.queue.fail_write = lambda _: (_ for _ in ()).throw(OSError())
                return response
            h.sender = accepted
            with self.assertRaisesRegex(RuntimeError, 'persistence failed'): h.run()
            self.assertEqual(len(h.sent), 1)
            self.assertEqual(self.control.data['state'], 'blocked')
            self.assertEqual(len(h.ledger['pending']), 1)
            h.queue.fail_write = None
            with self.assertRaises(circuit.Blocked): h.run()
            self.assertEqual(len(h.sent), 1)

    def test_crash_marker_does_not_expire_and_requires_manual_cas_resume(self):
        run = circuit.Run()
        run.start()
        # Represents a killed process: no finish/finally, durable marker remains.
        with self.assertRaises(circuit.Blocked): circuit.Run().start()
        before = copy.deepcopy(self.control.data)
        with self.assertRaises(circuit.Blocked): circuit.resume(str(self.control.sha), evidence='review')
        with patch.dict(os.environ, {'CP_ENABLE_LIVE_PUSH': '0', 'CP_ENABLE_ALL_OPTED_IN_ROLLOUT': '0'}):
            with self.assertRaises(circuit.Blocked): circuit.resume('old-sha', evidence='review', confirmed_no_inflight=True)
            self.assertEqual(self.control.data, before)
            circuit.resume(str(self.control.sha), evidence='incident-review-off-and-no-inflight', confirmed_no_inflight=True)
        with circuit.session(): circuit.current().check()
        self.assertEqual(self.control.data['state'], 'ready')

    def test_accepted_resets_consecutive_failures_and_existing_history_preserved(self):
        self.control.data['failures'] = 1
        with Harness(1, 1, real_circuit=True) as h:
            h.ledger['delivered'] = [format(i, '064x') for i in range(7)]
            h.ledger['pending'] = ['b'*64]
            h.run()
            self.assertEqual(self.control.data['failures'], 0)
            self.assertEqual(len(h.ledger['delivered']), 8)
            self.assertEqual(h.ledger['pending'], ['b'*64])
            h.run()
            self.assertEqual(len(h.sent), 1)

    def test_overlapping_worker_cannot_take_or_clear_owner(self):
        run = circuit.Run()
        run.start()
        with self.assertRaises(circuit.Blocked): circuit.Run().start()
        run.check()
        self.assertEqual(self.control.data['owner'], run.owner)
        run.finish()

    def test_two_real_threads_cannot_both_arm(self):
        barrier = threading.Barrier(2)
        local = threading.local()
        outcomes = []
        def simultaneous_read():
            value = self.control.read()
            if not getattr(local, 'read_once', False):
                local.read_once = True
                barrier.wait(timeout=3)
            return value
        def start():
            try:
                circuit.Run().start()
                outcomes.append('armed')
            except circuit.Blocked:
                outcomes.append('blocked')
        with patch.object(circuit, 'read', side_effect=simultaneous_read):
            threads = [threading.Thread(target=start) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=5)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, ['armed', 'blocked'])

    def test_control_write_failure_before_arming_never_sends(self):
        with Harness(1, 1, real_circuit=True) as h:
            with patch.object(circuit, 'write', side_effect=OSError('control unavailable')):
                with self.assertRaises(OSError): h.run()
            self.assertEqual(h.sent, [])
            self.assertEqual(h.ledger, dict(delivered=[], pending=[]))

    def test_export_auth_error_blocks_before_queue_mutation(self):
        with Harness(1, 1, real_circuit=True) as h:
            with patch.object(worker, 'request_export', side_effect=RuntimeError('authentication rejected')):
                with self.assertRaises(RuntimeError): h.run()
            self.assertEqual(self.control.data['state'], 'blocked')
            self.assertEqual(h.sent, [])
            self.assertEqual(h.queue.data['tasks'], {})

    def test_missing_control_and_unavailable_control_never_send(self):
        with Harness(1, 1, real_circuit=True) as h:
            with patch.object(circuit, 'read', return_value=(dict(version=1, state='blocked', failures=0), None)):
                with self.assertRaises(circuit.Blocked): h.run()
            self.control.fail = True
            with self.assertRaises(OSError): h.run()
            self.assertEqual(h.sent, [])

    def test_zero_target_clean_finish_and_preview_no_control_write(self):
        with Harness(0, 1, real_circuit=True) as h:
            h.run()
            self.assertEqual(self.control.data['state'], 'ready')
            sha = self.control.sha
            worker.process_window([], [], h.ledger, worker.datetime.now(worker.KST), current_ids=[], live=False)
            self.assertEqual(self.control.sha, sha)

class CircuitStorageTests(unittest.TestCase):
    def test_actual_private_format_roundtrip_and_readback(self):
        import base64, json
        saved = {}
        def request(url, token, method='GET', payload=None):
            self.assertTrue(url.endswith('/contents/push-delivery-control.json'))
            if method == 'PUT':
                self.assertEqual(payload['sha'], 'old')
                saved['data'] = json.loads(base64.b64decode(payload['content']))
            return dict(content=base64.b64encode(json.dumps(saved['data']).encode()).decode(), sha='new')
        data = dict(version=1, state='blocked', failures=2, reason='transport_uncertain')
        with patch.object(circuit, '_config', return_value=('private/fixture', 'fake')), patch.object(circuit, '_request', side_effect=request):
            self.assertEqual(circuit.write(data, 'old'), 'new')
            self.assertEqual(circuit.read(), (data, 'new'))

    def test_readback_mismatch_never_arms(self):
        with patch.object(circuit, '_config', return_value=('private/fixture', 'fake')), patch.object(circuit, '_request', return_value={}), patch.object(circuit, 'read', return_value=({}, 'new')):
            with self.assertRaises(circuit.Blocked): circuit.write(dict(state='armed'), 'old')

    def test_missing_and_permission_errors_fail_closed(self):
        from urllib.error import HTTPError
        for code in (404, 401, 403):
            with patch.object(circuit, '_config', return_value=('private/fixture', 'fake')), patch.object(circuit, '_request', side_effect=HTTPError('fake', code, 'error', {}, None)):
                if code == 404:
                    data, sha = circuit.read()
                    self.assertEqual(data['state'], 'blocked')
                    self.assertIsNone(sha)
                else:
                    with self.assertRaises(circuit.Blocked): circuit.read()
