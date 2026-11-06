#!/usr/bin/env python3
"""Read-only, reproducible input for the hourly AI writer; never publishes."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.threads_auto import candidates
from scripts.threads_writer_queue import fingerprint, validate_entry


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def build_input(now, limit=24):
    policy = load('threads/writer-policy.json')
    prompt = (ROOT / policy['prompt_path']).read_bytes()
    if hashlib.sha256(prompt).hexdigest() != policy['prompt_sha256']:
        raise ValueError('Master prompt hash differs from the approved policy')
    source, details, history, operations = [load(p) for p in
        ('alio.json', 'alio-detail.json', 'threads_posted.json', 'operations-status.json')]
    by_id = {p['id']: p for p in source['posts']}
    unconfirmed = set(operations.get('unconfirmed_ids', []))
    items = []
    # Preserve existing candidate exclusions; ALIO dates remain publication dates.
    # The AI writer independently verifies the actual application period.
    eligible = candidates(source['posts'], history, now.date())
    # Exact regular positions first, then original headcount ranking. Never relabel
    # permanent non-regular or fixed-term positions as regular employment.
    eligible.sort(key=lambda p: (
        -int('정규직' in str(details.get(p['id'], {}).get('hireTypeNmLst', '')).split(',')),
        -(p['count'] if p['count'] is not None else -1), p['days'], p['id']))
    for job in eligible:
        jid = job['id']
        if jid in unconfirmed or not details.get(jid):
            continue
        items.append({'notice_id': jid, 'source_post': by_id[jid],
                      'source_detail': details[jid],
                      'source_post_sha256': fingerprint(by_id[jid]),
                      'source_detail_sha256': fingerprint(details[jid])})
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
            'slots': slots, 'candidates': items,
            'all_blocked_notice_ids': sorted(set(history.get('posted_ids', [])) |
                {r['job_id'] for r in history.get('records', []) if r.get('job_id')}),
            'recent_records': history.get('records', [])[-10:],
            'pending_records': [r for r in history.get('records', []) if r.get('status') == 'pending'],
            'master_prompt': prompt.decode('utf-8')}


def check_queue(path, now):
    policy, source, details, history, operations = [load(p) for p in
        ('threads/writer-policy.json', 'alio.json', 'alio-detail.json',
         'threads_posted.json', 'operations-status.json')]
    if hashlib.sha256((ROOT / policy['prompt_path']).read_bytes()).hexdigest() != policy['prompt_sha256']:
        raise ValueError('Master prompt hash differs from the approved policy')
    source['_operations'] = operations
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
