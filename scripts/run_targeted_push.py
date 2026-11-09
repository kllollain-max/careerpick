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


def _require_send_guards_off(mode):
    if (os.environ.get('CP_ENABLE_LIVE_PUSH') != '0'
            or os.environ.get('CP_ENABLE_ALL_OPTED_IN_ROLLOUT') != '0'):
        raise RuntimeError(mode + ' requires both send guards OFF')


def _diagnostic_error(exc):
    """Only allowlisted codes enter public logs, never raw provider exceptions."""
    if isinstance(exc, HTTPError) and type(exc.code) is int and 100 <= exc.code <= 599:
        return {'error_code': 'http_rejected', 'http_status': exc.code}
    message = str(exc)
    match = re.fullmatch(r'(OneSignal export request|Private export download) rejected \(HTTP ([1-5][0-9]{2})\)', message)
    if match:
        return {'error_code': 'http_rejected', 'http_status': int(match[2])}
    match = re.fullmatch(r'OneSignal (?:subscriber|user) lookup HTTP error ([1-5][0-9]{2})', message)
    if match:
        return {'error_code': 'http_rejected', 'http_status': int(match[1])}
    match = re.fullmatch(
        r'Private export URL host not allowed \(provider category: (aws-s3|cloudfront|onesignal|onesignal-cdn|other)\); configure the exact verified host privately', message)
    if match:
        return {'error_code': 'export_host_not_allowed', 'provider_host_category': match[1]}
    codes = {
        'OneSignal export request network failure': 'export_request_network_failure',
        'OneSignal authentication or permissions rejected': 'subscriber_lookup_auth_rejected',
        'OneSignal subscriber lookup network error': 'subscriber_lookup_network_failure',
        'OneSignal user lookup network error': 'subscriber_lookup_network_failure',
        'Export URL not ready; retry in a separate controlled check': 'export_url_not_ready',
        'Private export not ready after bounded checks (HTTP 404)': 'export_not_ready_after_bounded_checks',
        'Invalid OneSignal app ID': 'invalid_app_id',
        'Missing private API key': 'missing_provider_key',
        'Invalid configured private export host': 'invalid_export_host_config',
        'Invalid private export URL': 'invalid_export_url',
        'Oversized export response': 'export_response_size_cap',
        'Invalid export response': 'invalid_export_response',
        'Private export redirect blocked': 'export_redirect_blocked',
        'Export redirects are not permitted': 'export_redirect_blocked',
        'Private export exceeds compressed size cap': 'export_compressed_size_cap',
        'Private export exceeds decompressed size cap': 'export_decompressed_size_cap',
        'Private export exceeds row cap': 'export_row_cap',
        'Invalid or oversized private subscription export': 'invalid_export_csv',
        'Invalid CSV encoding': 'invalid_export_csv',
        'Invalid export header': 'invalid_export_csv',
        'Missing subscription ID column': 'invalid_export_csv',
        'Malformed private export row': 'invalid_export_csv',
        'Private baseline not initialized or invalid': 'invalid_private_baseline',
        'Private delivery state not initialized': 'private_state_not_initialized',
        'Push control unavailable; no sending': 'control_unavailable',
        'Invalid push control; no sending': 'invalid_control',
        'Invalid private push checkpoint': 'invalid_private_cursor',
    }
    return {'error_code': codes.get(message, 'unclassified_diagnostic_error')}


def diagnose():
    """Read state and bounded provider export only; no delivery or state writes.

    Export subscription IDs stay in memory and are reported as a count only.
    A successful diagnosis never resumes a blocked circuit or authorizes sends.
    """
    _require_send_guards_off('Diagnose')  # Before even a private-state request.
    from scripts.private_onesignal_export_request import request_export
    from scripts.private_onesignal_export_download import read_export_ids
    from scripts.private_rollout_cursor import read_cursor
    from scripts.onesignal_known_subscriber import lookup
    report = {'mode': 'diagnose', 'status': 'diagnostic_failed', 'sent': 0,
              'state_changed': False, 'operator_review_required': True}
    stage = 'preflight'
    try:
        preflight()
        stage = 'ledger_read'
        ledger, ledger_sha = read_private_ledger()
        report['ledger'] = {'initialized': bool(ledger_sha),
                            'delivered_count': len(ledger.get('delivered', [])),
                            'pending_count': len(ledger.get('pending', []))}
        stage = 'baseline_read'
        baseline, baseline_sha = read_state(BASELINE)
        if (not baseline_sha or not isinstance(baseline, dict)
                or not isinstance(baseline.get('ids'), list)
                or any(not isinstance(value, str) or not value for value in baseline['ids'])):
            raise RuntimeError('Private baseline not initialized or invalid')
        report['baseline'] = {'initialized': True, 'known_job_count': len(baseline['ids'])}
        stage = 'queue_read'
        state, queue_sha = queue.read_queue()
        report['queue'] = {'initialized': bool(queue_sha), 'counts': queue.counts(state)}
        stage = 'control_read'
        control, control_sha = circuit.read()
        reasons = {'initial_review_required', 'run_in_progress', 'run_fault_review_required',
                   'operator_reviewed', 'run_completed', 'api_accepted'}
        report['control'] = {
            'initialized': bool(control_sha), 'state': control['state'],
            'reason_code': control.get('reason') if control.get('reason') in reasons else 'other_redacted',
            'failures': control['failures'],
            'sha': control_sha if isinstance(control_sha, str) and re.fullmatch(r'[0-9a-f]{40}', control_sha) else None,
        }
        if not ledger_sha or not queue_sha or not control_sha:
            raise RuntimeError('Private delivery state not initialized')
        report['operator_review_required'] = bool(
            control['state'] != 'ready' or ledger.get('pending')
            or report['queue']['counts']['reserved'] or report['queue']['counts']['uncertain'])
        stage = 'cursor_read'
        cursor, cursor_sha = read_cursor()
        report['cursor'] = {'initialized': bool(cursor_sha), 'next_index': cursor['next_index']}
        stage = 'export_request'
        url = request_export(os.environ.get('CP_ONESIGNAL_APP_ID', ''),
                             os.environ.get('CP_ONESIGNAL_REST_API_KEY', ''))
        stage = 'export_download'
        ids = read_export_ids(url)
        report['export'] = {'parsed_subscription_count': len(ids), 'consent_verified': False}
        # At most one exported subscription, through the existing read-only
        # identity/user lookup. It is never selected or authorized for delivery.
        stage = 'subscriber_lookup'
        subscriber = lookup(ids[0]) if ids else None
        report['lookup'] = {'sample_count': min(len(ids), 1),
                            'verified_opt_in_sample_count': int(bool(subscriber))}
        report['status'] = 'diagnostic_complete'
        report['stage'] = 'complete'
    except Exception as exc:
        report.update(stage=stage, operator_review_required=True, **_diagnostic_error(exc))
        report['missing_secrets'] = [key for key in REQUIRED if not os.environ.get(key, '').strip()]
    print(json.dumps(report, sort_keys=True))
    return report


def audit_consent():
    """Bounded, read-only opt-in audit; never print subscriber IDs or authorize sends."""
    _require_send_guards_off('Consent audit')
    from scripts.private_onesignal_export_request import request_export
    from scripts.private_onesignal_export_download import read_export_ids
    from scripts.onesignal_known_subscriber import lookup
    report = {'mode': 'audit-consent', 'status': 'audit_failed', 'sent': 0,
              'state_changed': False, 'operator_review_required': True}
    stage = 'preflight'
    try:
        preflight()
        stage = 'ledger_read'
        ledger, ledger_sha = read_private_ledger()
        stage = 'queue_read'
        state, queue_sha = queue.read_queue()
        stage = 'control_read'
        control, control_sha = circuit.read()
        if not ledger_sha or not queue_sha or not control_sha:
            raise RuntimeError('Private delivery state not initialized')
        counts = queue.counts(state)
        report['ledger'] = {'pending_count': len(ledger.get('pending', []))}
        report['queue'] = {'pending': counts['pending'], 'reserved': counts['reserved'],
                           'uncertain': counts['uncertain']}
        report['control'] = {'state': control['state']}
        stage = 'export_request'
        url = request_export(os.environ.get('CP_ONESIGNAL_APP_ID', ''),
                             os.environ.get('CP_ONESIGNAL_REST_API_KEY', ''))
        stage = 'export_download'
        ids = read_export_ids(url)
        report['export'] = {'parsed_subscription_count': len(ids)}
        # Never process an unexpectedly large export in this safety-only mode.
        if len(ids) > 20:
            report.update(status='audit_limit_exceeded', stage='audit_limit',
                          reviewed_count=0, verified_opt_in_count=0,
                          all_verified=False)
            print(json.dumps(report, sort_keys=True))
            return report
        stage = 'subscriber_lookup'
        verified = sum(bool(lookup(sid)) for sid in ids)
        report.update(status='audit_complete', stage='complete',
                      reviewed_count=len(ids), verified_opt_in_count=verified,
                      all_verified=bool(ids) and verified == len(ids)
                      and not ledger.get('pending')
                      and counts['reserved'] == 0 and counts['uncertain'] == 0)
    except Exception as exc:
        report.update(stage=stage, **_diagnostic_error(exc))
    print(json.dumps(report, sort_keys=True))
    return report


def resume_after_review():
    """Explicit operator CAS transition only; never called by scheduled run."""
    _require_send_guards_off('Resume')
    expected_sha = os.environ.get('CP_EXPECTED_CONTROL_SHA', '')
    evidence = os.environ.get('CP_PUSH_REVIEW_REFERENCE', '').strip()
    if not re.fullmatch(r'[0-9a-f]{40}', expected_sha):
        raise RuntimeError('Exact reviewed control SHA required')
    if not 1 <= len(evidence) <= 160 or any(ord(char) < 32 or ord(char) == 127 for char in evidence):
        raise RuntimeError('Bounded non-sensitive review reference required')
    # Reject a stale review or unresolved delivery before any provider request.
    def reviewed_state():
        ledger, ledger_sha = read_private_ledger()
        state, queue_sha = queue.read_queue()
        control, control_sha = circuit.read()
        if (not ledger_sha or not queue_sha or control_sha != expected_sha
                or control['state'] != 'blocked'):
            raise RuntimeError('Control changed or is not a reviewed blocked state')
        if ledger.get('pending') or any(task['state'] in {'reserved', 'uncertain'} for task in state['tasks'].values()):
            raise RuntimeError('Unresolved prior delivery; review without retransmission')
    preflight()
    reviewed_state()
    report = diagnose()
    if report['status'] != 'diagnostic_complete':
        raise RuntimeError('Read-only diagnosis failed; circuit remains blocked')
    # The export may take time; re-read inflight state before the final CAS.
    reviewed_state()
    new_sha = circuit.resume(expected_sha, evidence=evidence, confirmed_no_inflight=True)
    print(json.dumps({'mode': 'resume_after_review', 'resumed': True,
                      'sent': 0, 'history_preserved': True,
                      'control_sha': new_sha if isinstance(new_sha, str) and re.fullmatch(r'[0-9a-f]{40}', new_sha) else None}))


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
    now = detection.datetime.now(detection.KST)
    sources = ['alio']
    cleaneye_posts, _, _ = detection.cleaneye_snapshot(now)
    if cleaneye_posts is not None:
        ids = sorted(set(ids) | set(cleaneye_posts))
        sources.append('cleaneye')
    return {'ids': ids, 'initialized_sources': sources, 'updated': now.isoformat()}


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
    # Fail closed BEFORE candidate detection, backlog changes or baseline writes.
    # The sending worker also uses an atomic circuit session for delivery.
    control, control_sha = circuit.read()
    if not control_sha or control.get('state') != 'ready':
        raise circuit.Blocked('Push circuit requires operator review; no candidate updates or sending')
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
    if mode not in {'check', 'diagnose', 'audit-consent', 'initialize', 'resume_after_review', 'run'}:
        raise RuntimeError('Invalid push mode')
    if mode == 'diagnose':
        if diagnose()['status'] != 'diagnostic_complete':
            raise RuntimeError('Read-only diagnosis failed; no state change or sending')
        return
    if mode == 'audit-consent':
        if audit_consent()['status'] != 'audit_complete':
            raise RuntimeError('Read-only consent audit failed; no state change or sending')
        return
    if mode == 'resume_after_review':
        resume_after_review()
        return
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
