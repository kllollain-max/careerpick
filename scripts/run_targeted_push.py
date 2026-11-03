"""Restore the approved targeted sender; private state only, no historical broadcast."""
import base64
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from scripts.private_delivery_store import _config, _request, read_private_ledger
from scripts import private_push_delivery_queue as queue
from scripts import private_push_circuit_breaker as circuit
from scripts import detect_new_job_alerts as detection

BASELINE = 'push-detection-baseline.json'
REQUIRED = ('CP_ONESIGNAL_REST_API_KEY', 'CP_LEDGER_REPOSITORY', 'CP_LEDGER_TOKEN')


def preflight():
    missing = [key for key in REQUIRED if not os.environ.get(key, '').strip()]
    if missing:
        raise RuntimeError('Missing GitHub Secrets: ' + ', '.join(missing))
    repo, token = _config()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise RuntimeError('Invalid private state repository')
    meta = _request('https://api.github.com/repos/' + repo, token)
    if meta.get('private') is not True:
        raise RuntimeError('Delivery state repository must be private; no writes or sends')
    if repo.casefold() in {'kllollain-max/careerpick', 'jobinfo-hub/jobinfo-hub.github.io'}:
        raise RuntimeError('Cannot use public website for private delivery state')
    return repo, token


def read_state(name):
    repo, token = _config()
    try:
        value = _request('https://api.github.com/repos/' + repo + '/contents/' + name, token)
    except HTTPError as exc:
        if exc.code == 404:
            return None, None
        raise
    return json.loads(base64.b64decode(value['content'])), value['sha']


def save_state(name, state, sha):
    repo, token = _config()
    payload = {'message': 'Persist private targeted push state',
               'content': base64.b64encode(json.dumps(state, sort_keys=True).encode()).decode()}
    if sha is not None:
        payload['sha'] = sha
    _request('https://api.github.com/repos/' + repo + '/contents/' + name,
             token, method='PUT', payload=payload)
    restored, current_sha = read_state(name)
    if restored != state or not current_sha:
        raise RuntimeError('Private state readback failed; no replay')


def current_baseline():
    data = json.loads(Path('alio.json').read_text())
    ids = sorted({p['id'] for p in data['posts'] if p.get('type') == 'j' and p.get('alio')})
    if not ids or any(not re.fullmatch(r'a[0-9]+', value) for value in ids):
        raise RuntimeError('Invalid current ALIO baseline')
    return {'ids': ids, 'updated': detection.datetime.now(detection.KST).isoformat()}


def initialize():
    # Existing states are NEVER reset, resumed or overwritten by initialization.
    for name, empty in [('delivery-ledger.json', {'delivered': [], 'pending': []}),
                        ('candidate-backlog.json', {'version': 1, 'jobs': []}),
                        (queue.FILE, queue.empty_queue())]:
        existing, sha = read_state(name)
        if sha is None:
            save_state(name, empty, None)
    ledger, _ = read_private_ledger()
    data, _ = queue.read_queue()
    if ledger.get('pending') or any(x['state'] in {'reserved', 'uncertain'} for x in data['tasks'].values()):
        raise RuntimeError('Unresolved prior delivery; review without retransmission')
    previous, sha = read_state(BASELINE)
    if sha is None:
        save_state(BASELINE, current_baseline(), None)
    control, control_sha = circuit.read()
    if control_sha is None:
        # Owner approved future auto delivery. Bootstrap only, no notification.
        circuit.resume(None, evidence='Owner approved targeted automatic delivery 2026-11-03',
                       confirmed_no_inflight=True)
    elif control['state'] != 'ready':
        raise RuntimeError('Existing circuit requires separate incident review; not auto-resumed')
    print(json.dumps({'initialized': True, 'historical_jobs_enqueued': 0, 'sent': 0}))


def run():
    if (os.environ.get('CP_ENABLE_ALL_OPTED_IN_ROLLOUT') != '1'
            or os.environ.get('CP_ENABLE_LIVE_PUSH') != '1'):
        raise RuntimeError('Automatic push is OFF')
    baseline, sha = read_state(BASELINE)
    if sha is None or not isinstance(baseline, dict) or not isinstance(baseline.get('ids'), list):
        raise RuntimeError('Private baseline not initialized; no historical broadcast')
    detection.STATE.write_text(json.dumps(baseline))
    os.environ['CP_UPDATE_ALERT_STATE'] = '1'
    os.environ['CP_PERSIST_ALERT_BACKLOG'] = '1'
    os.environ['CP_ALERT_REPORT'] = '/tmp/careerpick-targeted-report.json'
    detection.main()  # read-back verified backlog BEFORE advancing durable baseline
    updated = json.loads(detection.STATE.read_text())
    # Retain seen IDs: removal/reappearance never becomes a new-job alert.
    updated['ids'] = sorted(set(updated['ids']) | set(baseline['ids']))
    save_state(BASELINE, updated, sha)
    from scripts.send_all_opted_in_bounded import main
    main()


def main():
    mode = os.environ.get('CP_PUSH_MODE', 'check')
    if mode not in {'check', 'initialize', 'run'}:
        raise RuntimeError('Invalid push mode')
    preflight()
    if mode == 'initialize':
        if os.environ.get('CP_ENABLE_LIVE_PUSH') != '0' or os.environ.get('CP_ENABLE_ALL_OPTED_IN_ROLLOUT') != '0':
            raise RuntimeError('Initialize requires both send guards OFF')
        initialize()
    elif mode == 'run':
        run()
    else:
        ledger, sha = read_private_ledger()
        baseline, baseline_sha = read_state(BASELINE)
        state, _ = queue.read_queue()
        control, control_sha = circuit.read()
        if not sha or not baseline_sha or not control_sha or control['state'] != 'ready':
            raise RuntimeError('Private state initialization/review required')
        print(json.dumps({'ready': True, 'sent': 0, 'queue_counts': queue.counts(state),
                          'reserved_count': len(ledger.get('pending', []))}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Third-party payloads/URLs/IDs/credentials never enter public logs.
        missing = [key for key in REQUIRED if not os.environ.get(key, '').strip()]
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__, 'missing_secrets': missing}))
        raise SystemExit('Targeted push stopped; private state review required; no automatic replay') from None
