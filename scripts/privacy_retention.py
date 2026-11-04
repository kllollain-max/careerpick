"""Review-only retention decisions from minimal metadata.

No network clients, credentials, storage mutations, provider deletion or live
workflow integration. A candidate is never permission to execute deletion.
CLI stdin accepts metadata only; stdout contains aggregate counts only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
import sys

UTC = timezone.utc
MAX_BYTES = 1_048_576
MAX_RECORDS = 10_000
POLICY_VERSION = 'careerpick-retention-review-v1'
KINDS = {'local_record', 'inquiry', 'push_subscription', 'delivery_log', 'dedup_record', 'backup_copy'}
BOOLS = {'event_verified', 'follow_up_required', 'identity_verified', 'opted_in', 'unresolved', 'legal_basis_verified'}
TIMES = {'event_at', 'purpose_ended_at', 'follow_up_ended_at', 'last_contact_at', 'revocation_at', 'legal_hold_until', 'original_deadline_at'}
FIELDS = {'kind'} | BOOLS | TIMES
GATES = {'scope_verified', 'all_copies_accounted_for', 'restore_protection_verified', 'provider_scope_verified', 'replay_prevention_verified'}


class MetadataError(ValueError):
    """Fixed errors only; never include input values in diagnostics."""


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    deadline: datetime | None = None
    overdue: bool = False
    stop_delivery_candidate: bool = False


def instant(value):
    if not isinstance(value, str):
        raise MetadataError('invalid_timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise MetadataError('invalid_timestamp') from None


def _validate(record, now, evidence):
    if not isinstance(record, dict) or set(record) - FIELDS or record.get('kind') not in KINDS:
        raise MetadataError('unsupported_metadata')
    if not isinstance(evidence, dict) or set(evidence) - GATES or any(type(v) is not bool for v in evidence.values()):
        raise MetadataError('invalid_evidence')
    if any(type(record[k]) is not bool for k in BOOLS if k in record):
        raise MetadataError('invalid_boolean')
    dates = {k: instant(record[k]) for k in TIMES if k in record}
    if any(v > now for k, v in dates.items() if k not in {'legal_hold_until', 'original_deadline_at'}):
        raise MetadataError('future_event_timestamp')
    if 'event_at' in dates:
        if any(dates[k] < dates['event_at'] for k in ['purpose_ended_at', 'follow_up_ended_at', 'revocation_at'] if k in dates):
            raise MetadataError('invalid_event_order')
    if 'purpose_ended_at' in dates and 'follow_up_ended_at' in dates and dates['follow_up_ended_at'] < dates['purpose_ended_at']:
        raise MetadataError('invalid_event_order')
    return dates


def _candidate(kind, reason, deadline, now, evidence, stop=False):
    required = {'scope_verified', 'all_copies_accounted_for', 'restore_protection_verified'}
    if kind == 'push_subscription':
        required.add('provider_scope_verified')
    if kind == 'dedup_record':
        required.add('replay_prevention_verified')
    if any(evidence.get(key) is not True for key in required):
        return Decision('blocked', 'deletion_prerequisites_incomplete', deadline, now > deadline, stop)
    return Decision('delete_candidate', reason, deadline, now > deadline, stop)


def decide(record, *, now, evidence=None):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise MetadataError('aware_clock_required')
    now = now.astimezone(UTC)
    evidence = {} if evidence is None else evidence
    try:
        dates = _validate(record, now, evidence)
    except MetadataError as error:
        return Decision('blocked', str(error))
    kind = record['kind']
    # User-controlled browser files are never an operator purge target.
    if kind == 'local_record':
        return Decision('client_managed', 'user_controls_local_records')
    revoked = dates.get('revocation_at')
    stop = kind == 'push_subscription' and revoked is not None and record.get('identity_verified') is True
    if record.get('unresolved') is True:
        target = None
        if record.get('event_verified') is True and dates.get('event_at') is not None and kind in {'delivery_log', 'dedup_record'}:
            target = dates['event_at'] + timedelta(days=30 if kind == 'delivery_log' else 90)
        return Decision('blocked', 'unresolved_delivery_requires_review', target,
                        target is not None and now > target, stop)
    if 'legal_hold_until' in dates:
        if record.get('legal_basis_verified') is not True:
            return Decision('blocked', 'legal_hold_basis_unverified', stop_delivery_candidate=stop)
        if dates['legal_hold_until'] > now:
            return Decision('restricted_hold', 'documented_legal_hold_only', dates['legal_hold_until'], stop_delivery_candidate=stop)
    if record.get('event_verified') is not True:
        return Decision('blocked', 'legacy_or_unverified_event', stop_delivery_candidate=stop)
    if kind == 'push_subscription':
        if revoked is None:
            if record.get('opted_in') is True:
                return Decision('keep', 'subscription_purpose_active')
            return Decision('blocked', 'revocation_event_required')
        if record.get('identity_verified') is not True:
            return Decision('blocked', 'subject_control_unverified')
        # Five days is an internal completion target, never a waiting period.
        return _candidate(kind, 'confirmed_revocation_delete_without_delay', revoked + timedelta(days=5), now, evidence, True)
    if kind == 'backup_copy':
        deadline = dates.get('original_deadline_at')
        if deadline is None:
            return Decision('blocked', 'original_retention_deadline_missing')
    elif kind == 'inquiry':
        ended = dates.get('purpose_ended_at')
        if ended is None:
            contact = dates.get('last_contact_at')
            if contact is None:
                return Decision('blocked', 'last_real_contact_missing')
            review_at = contact + timedelta(days=30)
            if now >= review_at:
                return Decision('review_closure', 'unanswered_inquiry_review_not_auto_delete', review_at, now > review_at)
            return Decision('keep', 'inquiry_processing_active', review_at)
        if record.get('follow_up_required') is True:
            deadline = min(ended + timedelta(days=30), dates.get('follow_up_ended_at', ended + timedelta(days=30)))
        else:
            deadline = ended
    else:
        event = dates.get('event_at')
        if event is None:
            return Decision('blocked', 'original_event_time_missing')
        deadline = event + timedelta(days=30 if kind == 'delivery_log' else 90)
        if dates.get('purpose_ended_at') is not None:
            deadline = min(deadline, dates['purpose_ended_at'])
    if now < deadline:
        return Decision('keep', 'purpose_bound_cap_not_reached', deadline)
    return _candidate(kind, 'retention_or_purpose_ended', deadline, now, evidence)


def review(records, *, now, evidence=None):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise MetadataError('aware_clock_required')
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise MetadataError('invalid_record_batch')
    if evidence is not None and (not isinstance(evidence, dict) or set(evidence) - GATES
                                 or any(type(v) is not bool for v in evidence.values())):
        raise MetadataError('invalid_evidence')
    decisions = [decide(row, now=now, evidence=evidence) for row in records]
    return {
        'policy_version': POLICY_VERSION,
        'mode': 'review_only',
        'records_reviewed': len(records),
        'actions': dict(sorted(Counter(x.action for x in decisions).items())),
        'reasons': dict(sorted(Counter(x.reason for x in decisions).items())),
        'overdue_review_count': sum(x.overdue for x in decisions),
        'stop_delivery_candidates': sum(x.stop_delivery_candidate for x in decisions),
        'actual_deleted': 0,
        'actual_notifications_sent': 0,
        'live_activation_ready': False,
    }


def audit_legacy(ledger, queue):
    """Count existing formats without echoing keys, subjects or message IDs.

    No timestamps are inferred or introduced; an empty live snapshot does not
    establish the absence of data at providers, in Git history or in email.
    """
    if not isinstance(ledger, dict) or not isinstance(queue, dict):
        raise MetadataError('invalid_legacy_state')
    fields = [ledger.get('delivered'), ledger.get('pending', [])]
    if any(not isinstance(rows, list) or any(not isinstance(k, str) or not re.fullmatch('[0-9a-f]{64}', k) for k in rows) for rows in fields):
        raise MetadataError('invalid_legacy_ledger')
    if len(set(fields[0])) != len(fields[0]) or len(set(fields[1])) != len(fields[1]) or set(fields[0]) & set(fields[1]):
        raise MetadataError('conflicting_legacy_ledger')
    tasks = queue.get('tasks')
    if type(queue.get('version')) is not int or queue['version'] != 1 or not isinstance(tasks, dict):
        raise MetadataError('invalid_legacy_queue')
    if any(not re.fullmatch('[0-9a-f]{64}', str(k)) or not isinstance(v, dict) or v.get('state') not in {'pending', 'reserved', 'accepted', 'failed', 'uncertain'} for k, v in tasks.items()):
        raise MetadataError('invalid_legacy_queue')
    return {
        'ledger_delivered': len(fields[0]), 'ledger_pending': len(fields[1]),
        'queue_records': len(tasks),
        'queue_unresolved': sum(v['state'] in {'reserved', 'uncertain'} for v in tasks.values()),
        # Current v1 formats do not contain authoritative retention metadata.
        'legacy_records_requiring_timestamp_review': len(fields[0]) + len(fields[1]) + len(tasks),
        'actual_deleted': 0, 'history_and_provider_coverage': 'not_verified',
    }


def example(now):
    old = (now - timedelta(days=100)).isoformat()
    return [
        {'kind': 'local_record'},
        {'kind': 'inquiry', 'event_verified': True, 'purpose_ended_at': old},
        {'kind': 'push_subscription', 'event_verified': True, 'revocation_at': now.isoformat(), 'identity_verified': True},
        {'kind': 'delivery_log', 'event_verified': True, 'event_at': old},
        {'kind': 'dedup_record', 'event_verified': True, 'event_at': old},
        {'kind': 'delivery_log'},
    ]


class ReviewParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default message may echo an unknown argument's value.
        self.exit(2, 'Invalid review-only arguments.\n')


def main(argv=None):
    parser = ReviewParser(description='Offline metadata review only; no apply mode')
    parser.add_argument('--example', action='store_true', help='Use only built-in synthetic metadata')
    parser.add_argument('--at', help='Explicit timezone-aware review clock')
    args = parser.parse_args(argv)
    try:
        now = instant(args.at) if args.at else datetime.now(UTC)
        if args.example:
            rows, evidence = example(now), {}
        else:
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise MetadataError('input_too_large')
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                raise MetadataError('invalid_metadata_json') from None
            if not isinstance(payload, dict) or set(payload) - {'records', 'evidence'}:
                raise MetadataError('unsupported_metadata_envelope')
            rows, evidence = payload.get('records'), payload.get('evidence', {})
        print(json.dumps(review(rows, now=now, evidence=evidence), sort_keys=True))
        return 0
    except MetadataError:
        print(json.dumps({'mode': 'review_only', 'status': 'blocked', 'error': 'invalid_or_unsupported_metadata', 'actual_deleted': 0}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
