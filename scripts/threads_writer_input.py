#!/usr/bin/env python3
"""Read-only, reproducible input for the hourly AI writer; never publishes."""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.threads_auto import MIN_DAYS, MAX_DAYS, candidates, writer_inputs
from scripts.threads_writer_queue import fingerprint, validate_entry
from scripts.cleaneye_source_adapter import SourceValidationError, validate_cleaneye_feed, validate_cleaneye_post


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def build_input(now, limit=24):
    if type(limit) is not int or not 1 <= limit <= 60:
        raise ValueError('limit must be 1 to 60')
    policy, source, details = writer_inputs(ROOT)
    prompt = (ROOT / policy['prompt_path']).read_bytes()
    history, operations = load('threads_posted.json'), source['_operations']
    by_id = {p['id']: p for p in source['posts']}
    source_details = dict(details)
    unconfirmed = set(operations.get('unconfirmed_ids', []))
    blocked = set(history.get('posted_ids', [])) | {
        r['job_id'] for r in history.get('records', []) if r.get('job_id')}
    blocked.update(jid for r in history.get('records', []) for jid in r.get('job_ids', []))
    items = []
    # Preserve existing candidate exclusions; ALIO dates remain publication dates.
    # The AI writer independently verifies the actual application period.
    eligible = candidates(source['posts'], history, now.date())
    cleaneye = source.get('_cleaneye', {})
    cleaneye_facts = {}
    cleaneye_status = 'verified'
    try:
        validate_cleaneye_feed(cleaneye, now, max_age_hours=policy['max_source_age_hours'])
    except SourceValidationError as error:
        cleaneye_status = str(error)
    else:
        for post in cleaneye['posts']:
            if post['id'] in blocked:
                continue
            try:
                facts = validate_cleaneye_post(post, cleaneye, now, max_age_hours=policy['max_source_age_hours'])
            except SourceValidationError:
                continue
            # Use the same 5–20-day selection window and one shared output cap.
            days = (datetime.fromisoformat(facts['application_period']['end']).date() - now.date()).days
            if not MIN_DAYS <= days <= MAX_DAYS:
                continue
            jid = post['id']
            by_id[jid], source_details[jid], cleaneye_facts[jid] = post, post['cleaneyeDetail'], facts
            eligible.append({'id': jid, 'count': facts['count'], 'days': days})
    # Exact regular positions first, then original headcount ranking. Never relabel
    # permanent non-regular or fixed-term positions as regular employment.
    eligible.sort(key=lambda p: (
        -int(any(label.strip() in {'정규직', '일반정규직'}
                 for label in re.split(r'[,/;·|]', cleaneye_facts[p['id']]['employment']))
             if p['id'] in cleaneye_facts else '정규직' in str(details.get(p['id'], {}).get('hireTypeNmLst', '')).split(',')),
        -(p['count'] if p['count'] is not None else -1), p['days'], p['id']))
    for job in eligible:
        jid = job['id']
        if jid in blocked or jid in unconfirmed or not source_details.get(jid):
            continue
        context = cleaneye_facts.get(jid)
        items.append({'notice_id': jid,
                      **({'source': 'cleaneye', 'official_id': context['official_id'], 'source_context': context}
                         if context else {}),
                      'source_post': by_id[jid], 'source_detail': source_details[jid],
                      'source_post_sha256': fingerprint(by_id[jid]),
                      'source_detail_sha256': fingerprint(source_details[jid])})
        if len(items) >= limit:
            break
    slots = []
    for offset in range(2):
        day = (now + timedelta(days=offset)).date()
        for hour in policy['slots']:
            at = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour)
            if now < at <= now + timedelta(hours=24):
                slots.append({'scheduled_at': at.isoformat(),
                              'format_id': policy['formats'][f'{hour:02d}']})
    return {'reference_at': now.isoformat(), 'policy': policy,
            'source_updated': source.get('updated'), 'operations': operations,
            'cleaneye_source': {'status': cleaneye_status, 'updated': cleaneye.get('updated') if isinstance(cleaneye, dict) else None},
            'slots': slots, 'candidates': items,
            'all_blocked_notice_ids': sorted(blocked),
            'recent_records': history.get('records', [])[-10:],
            'pending_records': [r for r in history.get('records', []) if r.get('status') == 'pending'],
            'master_prompt': prompt.decode('utf-8')}


def check_queue(path, now):
    policy, source, details = writer_inputs(ROOT)
    history = load('threads_posted.json')
    queue = json.loads(Path(path).read_text(encoding='utf-8'))
    if queue.get('schema_version') != 1 or not isinstance(queue.get('entries'), list):
        raise ValueError('Invalid queue schema')
    slots, notices, checked = set(), set(), []
    for entry in queue['entries']:
        scheduled = datetime.fromisoformat(entry['scheduled_at'])
        if scheduled.tzinfo is None or scheduled in slots:
            raise ValueError('Duplicate or naive queue slot')
        slots.add(scheduled)
        reserved = [r for r in history['records'] if r.get('scheduled_at') == entry['scheduled_at']]
        if reserved:
            if len(reserved) != 1 or reserved[0].get('queue_entry_sha256') != fingerprint(entry):
                raise ValueError('An already reserved queue entry was changed')
            continue
        if scheduled < now - timedelta(hours=2):
            continue
        if entry.get('notice_id') in notices:
            raise ValueError('One notice is assigned to multiple upcoming slots')
        notices.add(entry.get('notice_id'))
        if entry.get('writer', {}).get('status') != 'ready':
            continue
        validate_entry(entry, scheduled, now, history, source, details, policy)
        checked.append({'scheduled_at': entry['scheduled_at'], 'notice_id': entry['notice_id'],
                        'format_id': entry['format_id'], 'chars': len(entry['writer']['post_text'])})
    return {'status': 'validated', 'ready_entries': checked}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=24)
    parser.add_argument('--check-queue', help='Validate upcoming ready drafts without sending')
    args = parser.parse_args()
    if not 1 <= args.limit <= 60:
        parser.error('limit must be 1 to 60')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    output = check_queue(args.check_queue, now) if args.check_queue else build_input(now, args.limit)
    print(json.dumps(output, ensure_ascii=False, indent=2))
