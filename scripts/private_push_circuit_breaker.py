"""Private, sticky write-ahead circuit for the scheduled and scoped push paths.

An armed run is a durable stop marker until it cleanly finishes. Missing state,
read/write ambiguity, crashes and expired owners never auto-resume. No secrets
or recipient identifiers are stored. Reuse the existing private GitHub store.
"""
import base64
import json
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.error import HTTPError
from scripts.private_delivery_store import _config, _request

FILE = 'push-delivery-control.json'
THRESHOLD = 2
_ACTIVE = ContextVar('push_control', default=None)


class Blocked(RuntimeError):
    pass


def read():
    repo, token = _config()
    try:
        value = _request('https://api.github.com/repos/' + repo + '/contents/' + FILE, token)
    except HTTPError as error:
        if error.code == 404:
            return dict(version=1, state='blocked', failures=0, reason='initial_review_required'), None
        raise Blocked('Push control unavailable; no sending') from None
    data = json.loads(base64.b64decode(value['content']))
    if (data.get('version') != 1 or data.get('state') not in {'ready', 'armed', 'blocked'}
            or type(data.get('failures')) is not int or data['failures'] < 0):
        raise Blocked('Invalid push control; no sending')
    return data, value['sha']


def write(data, sha):
    repo, token = _config()
    payload = dict(message='Advance private push safety control',
                   content=base64.b64encode((json.dumps(data, sort_keys=True)+'\n').encode()).decode())
    if sha is not None:
        payload['sha'] = sha
    _request('https://api.github.com/repos/' + repo + '/contents/' + FILE,
             token, method='PUT', payload=payload)
    saved, saved_sha = read()
    if saved != data:
        raise Blocked('Push control readback mismatch; no sending')
    return saved_sha


def resume(expected_sha, *, evidence, confirmed_no_inflight=False):
    """Operator-only CAS resume after OFF, in-flight/uncertain review and repair.

    Never called by a sender, scheduler or timeout. Initial missing state also
    requires this explicit review. Evidence is a non-secret review reference.
    """
    if (confirmed_no_inflight is not True
            or os.environ.get('CP_ENABLE_LIVE_PUSH') != '0'
            or os.environ.get('CP_ENABLE_ALL_OPTED_IN_ROLLOUT') != '0'):
        raise Blocked('Resume requires both local send guards OFF and explicit in-flight review')
    if not isinstance(evidence, str) or not 1 <= len(evidence) <= 160:
        raise ValueError('Review reference required')
    _, sha = read()
    if sha != expected_sha:
        raise Blocked('Control changed since review; inspect again')
    return write(dict(version=1, state='ready', failures=0, reason='operator_reviewed',
                      review=evidence), sha)


class Run:
    def __init__(self):
        self.owner = uuid.uuid4().hex

    def check(self):
        data, sha = read()
        if data['state'] != 'armed' or data.get('owner') != self.owner:
            raise Blocked('Global push circuit closed to sends')
        return data, sha

    def start(self):
        data, sha = read()
        if sha is None or data['state'] != 'ready':
            raise Blocked('Push circuit requires operator review; no sending')
        write(dict(data, state='armed', owner=self.owner, reason='run_in_progress'), sha)
        self.check()

    def failure(self, reason, *, immediate=False):
        data, sha = self.check()
        failures = data['failures'] + 1
        stopped = immediate or failures >= THRESHOLD
        write(dict(data, failures=failures, state='blocked' if stopped else 'armed',
                   reason=reason), sha)
        if stopped:
            raise Blocked('Global push circuit tripped; operator review required')

    def success(self):
        data, sha = self.check()
        if data['failures']:
            write(dict(data, failures=0, reason='api_accepted'), sha)

    def finish(self):
        data, sha = self.check()
        write(dict(data, state='ready', owner=None, reason='run_completed'), sha)

    def abort(self):
        # If storage/permission is down, the pre-saved armed marker remains a
        # sticky global block. Never claim a blocked write succeeded in that case.
        try:
            data, sha = self.check()
            write(dict(data, state='blocked', reason='run_fault_review_required'), sha)
        except Exception:
            pass


@contextmanager
def session():
    active = _ACTIVE.get()
    if active is not None:
        yield active
        return
    run = Run()
    run.start()  # CAS/readback before ANY provider call or delivery-state write
    token = _ACTIVE.set(run)
    try:
        yield run
        run.finish()
    except BaseException:
        run.abort()
        raise
    finally:
        _ACTIVE.reset(token)


def current():
    run = _ACTIVE.get()
    if run is None:
        raise Blocked('No durable push safety session')
    return run
