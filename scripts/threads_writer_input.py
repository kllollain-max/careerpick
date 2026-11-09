#!/usr/bin/env python3
"""Read-only, reproducible input for the hourly AI writer; never publishes."""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.threads_auto import writer_inputs
from scripts.threads_writer_queue import fingerprint, validate_entry
from scripts.threads_candidate_selection import build_selection
from scripts.threads_reach_editorial import load_editorial_prompt, balanced_hook_type


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def build_input(now, limit=24, reviewed_entries=None):
    if type(limit) is not int or not 1 <= limit <= 60:
        raise ValueError('limit must be 1 to 60')
    policy, source, details = writer_inputs(ROOT)
    prompt = (ROOT / policy['prompt_path']).read_bytes()
    editorial_prompt = load_editorial_prompt(ROOT, policy)
    history, operations = load('threads_posted.json'), source['_operations']
    selection = build_selection(source, details, history, policy, now, limit, reviewed_entries)
    cleaneye = source.get('_cleaneye', {})
    slots = []
    for offset in range(2):
        day = (now + timedelta(days=offset)).date()
        for hour in policy['slots']:
            at = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour)
            if now < at <= now + timedelta(hours=24):
                slots.append({'scheduled_at': at.isoformat(),
                              'format_id': policy['formats'][f'{hour:02d}'],
                              **({'hook_type': balanced_hook_type(at, datetime.fromisoformat(
                                  policy['editorial_policy']['effective_at']).date())}
                                 if editorial_prompt else {})})
    return {'reference_at': now.isoformat(), 'policy': policy,
            'source_updated': source.get('updated'), 'operations': operations,
            'cleaneye_source': {'status': selection['cleaneye_status'], 'updated': cleaneye.get('updated') if isinstance(cleaneye, dict) else None},
            'slots': slots, 'candidates': selection['candidates'],
            'selection_audit': selection['selection_audit'],
            'review_candidates': selection['review_candidates'],
            'all_blocked_notice_ids': selection['all_blocked_notice_ids'],
            'recent_records': history.get('records', [])[-10:],
            'pending_records': [r for r in history.get('records', []) if r.get('status') == 'pending'],
            'master_prompt': prompt.decode('utf-8'),
            'editorial_prompt': editorial_prompt}


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
        selected = validate_entry(entry, scheduled, now, history, source, details, policy)
        from scripts.threads_auto import master_public_copy
        main, detail = master_public_copy(selected, policy.get('publication_style'))
        checked.append({'scheduled_at': entry['scheduled_at'], 'notice_id': entry['notice_id'],
                        'format_id': entry['format_id'], 'chars': len(entry['writer']['post_text']),
                        'public_preview': {'main_text': main, 'detail_reply': detail},
                        'editorial_policy_id': entry.get('editorial_policy_id')})
    return {'status': 'validated', 'ready_entries': checked}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=24)
    parser.add_argument('--check-queue', help='Validate upcoming ready drafts without sending')
    parser.add_argument('--queue-for-selection', help='Freshly read queue JSON; validate evidence before using unit facts for selection')
    args = parser.parse_args()
    if not 1 <= args.limit <= 60:
        parser.error('limit must be 1 to 60')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    reviewed = None
    if args.queue_for_selection:
        selection_queue = json.loads(Path(args.queue_for_selection).read_text(encoding='utf-8'))
        if selection_queue.get('schema_version') != 1 or not isinstance(selection_queue.get('entries'), list):
            raise ValueError('Invalid selection review queue schema')
        reviewed = selection_queue['entries']
    output = check_queue(args.check_queue, now) if args.check_queue else build_input(now, args.limit, reviewed)
    print(json.dumps(output, ensure_ascii=False, indent=2))
