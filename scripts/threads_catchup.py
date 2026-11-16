"""Explicit same-day recovery of a missing slot using an independently reviewed entry.

The normal selector keeps its two-hour grace. This separate path requires an
explicit first-attempt dispatch, a genuine current nonce, complete live Meta
inventory, unchanged official bytes and the existing unmodified manuscript
validator. It never changes a future regular entry or grants draft approval.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')


def recovery_slot(value, now):
    if (os.getenv('THREADS_RECOVERY_CONFIRMATION') != 'RECOVER_SLOT'
            or os.getenv('THREADS_MANUAL_PUBLISH', '').lower() != 'true'
            or os.getenv('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or os.getenv('GITHUB_RUN_ATTEMPT', '1') != '1'):
        raise RuntimeError('CATCHUP_EXPLICIT_FIRST_DISPATCH_REQUIRED')
    try:
        slot = datetime.fromisoformat(value)
        if (slot.utcoffset() != timedelta(hours=9) or slot.hour not in (8,12,16,20)
                or slot.minute or slot.second or slot.microsecond
                or now.utcoffset() is None or slot.date() != now.astimezone(KST).date()
                or not slot + timedelta(hours=2) <= now):
            raise ValueError
    except (ValueError, TypeError):
        raise RuntimeError('CATCHUP_SAME_DAY_MISSED_SLOT_REQUIRED') from None
    return slot


def read_live_inventory(root, now):
    from scripts.threads_auto import api
    from scripts.threads_live_inventory import inventory
    report = inventory(api, os.environ['THREADS_ACCESS_TOKEN'],
                       os.environ['THREADS_USER_ID'], now)
    (Path(root)/'threads-live-inventory.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


def validate_inventory(report, entry, slot, now, history):
    try:
        checked = datetime.fromisoformat(report['checked_at'])
        start = datetime.fromisoformat(report['window_start'])
        if (report.get('schema_version') != 1 or report.get('account') != 'hid_119'
                or report.get('pagination_complete') is not True
                or checked.utcoffset() is None or start.utcoffset() is None
                or not timedelta(0) <= now-checked <= timedelta(minutes=10)
                or not start <= slot <= checked or not isinstance(report.get('posts'), list)):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise RuntimeError('CATCHUP_COMPLETE_FRESH_INVENTORY_REQUIRED') from None
    known = {str(r.get('threads_post_id')) for r in history['records']
             if r.get('status') == 'published' and r.get('threads_post_id')}
    digest = hashlib.sha256(entry['writer']['post_text'].encode()).hexdigest()
    seen, today = set(), 0
    for post in report['posts']:
        try:
            identifier = str(post['post_id'])
            stamp = datetime.fromisoformat(post['timestamp'])
            if (not identifier.isdigit() or identifier in seen or stamp.utcoffset() is None
                    or not start <= stamp <= checked or type(post.get('is_reply')) is not bool):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise RuntimeError('CATCHUP_INVENTORY_POST_INVALID') from None
        seen.add(identifier)
        if post.get('text_sha256') == digest:
            raise RuntimeError('CATCHUP_TEXT_ALREADY_PUBLISHED')
        if not post['is_reply'] and stamp.astimezone(KST).date() == now.astimezone(KST).date():
            today += 1
            if identifier not in known:
                raise RuntimeError('CATCHUP_UNRECONCILED_REMOTE_POST')
    if today >= 4:
        raise RuntimeError('CATCHUP_DAILY_LIMIT_REACHED')


def select_recovery(queue, slot, now, history, source, details, policy, notice_id, report):
    from scripts.threads_writer_queue import validate_entry
    # Recheck dispatch intent even immediately before sending an old reservation.
    if recovery_slot(slot.isoformat(), now) != slot:
        raise RuntimeError('CATCHUP_SLOT_MISMATCH')
    if (not isinstance(queue, dict) or queue.get('schema_version') != 1
            or not isinstance(queue.get('entries'), list) or len(queue['entries']) != 1):
        raise RuntimeError('CATCHUP_ONE_REVIEWED_ENTRY_REQUIRED')
    entry = queue['entries'][0]
    if (not isinstance(entry, dict) or not notice_id or entry.get('notice_id') != notice_id
            or entry.get('recovery_for_slot') != slot.isoformat()
            or entry.get('scheduled_at') != slot.isoformat()):
        raise RuntimeError('CATCHUP_ENTRY_BINDING_REQUIRED')
    if any(r.get('scheduled_at') == slot.isoformat() for r in history['records']):
        raise RuntimeError('CATCHUP_SLOT_ALREADY_RECORDED')
    if any(r.get('status') == 'pending' and not r.get('threads_post_id') for r in history['records']):
        raise RuntimeError('CATCHUP_UNRESOLVED_PRIOR_RESERVATION')
    day = now.astimezone(KST).date().isoformat()
    if sum(r.get('reserved_date') == day and r.get('status') in ('pending','published')
           for r in history['records']) >= 4:
        raise RuntimeError('CATCHUP_DAILY_LIMIT_REACHED')
    selected = validate_entry(entry, slot, now, history, source, details, policy)
    if not selected.get('writer_review', {}).get('v5'):
        raise RuntimeError('CATCHUP_V5_REVIEW_REQUIRED')
    validate_inventory(report, entry, slot, now, history)
    from scripts.threads_reviewed_ingest import verify_official_receipt
    verify_official_receipt(entry)
    return selected
