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


def build_input(now, limit=24, reviewed_entries=None, *, queued_entries=None):
    if type(limit) is not int or not 1 <= limit <= 60:
        raise ValueError('limit must be 1 to 60')
    policy, source, details = writer_inputs(ROOT)
    prompt = (ROOT / policy['prompt_path']).read_bytes()
    editorial_prompt = load_editorial_prompt(ROOT, policy)
    history, operations = load('threads_posted.json'), source['_operations']
    selection = build_selection(source, details, history, policy, now, limit, reviewed_entries, queued_entries=queued_entries)
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
    from scripts.threads_v5 import load_prompt, FORMATS, balanced_intro_type
    v5_prompt = load_prompt(ROOT, policy)
    if policy.get('editorial_v5', {}).get('enabled'):
        confirmed = [r for r in history.get('records', [])
                     if r.get('status') == 'published' and r.get('threads_post_id')]
        prior = next((r for r in reversed(confirmed) if 'image_url' in r), None)
        next_media = 'IMAGE' if prior is not None and not prior.get('image_url') else 'TEXT'
        planning_history = list(confirmed)
        for slot in slots:
            scheduled = datetime.fromisoformat(slot['scheduled_at'])
            slot['format_id'] = FORMATS[f"{scheduled.hour:02}"]
            slot['hook_type'] = balanced_intro_type(scheduled, planning_history, next_media)
            slot['planned_media'] = next_media
            slot['experiment_variable'] = 'intro_target_vs_condition_only'
            slot['planning_only_recheck_actual_success_history'] = True
            # Balance the planning batch too; this synthetic row is never saved
            # to the publication history or counted as a published observation.
            planning_history.append({'status': 'published', 'threads_post_id': 'planning-only',
                'scheduled_at': slot['scheduled_at'], 'image_url': 'planned' if next_media == 'IMAGE' else '',
                'writer_review': {'v5': {'policy_id': policy['editorial_v5']['id'],
                    'contract_version': 2, 'first_sentence_type': slot['hook_type']}}})
            next_media = 'TEXT' if next_media == 'IMAGE' else 'IMAGE'
    return {'v5_prompt': v5_prompt, 'v5_enabled': policy.get('editorial_v5', {}).get('enabled', False),
            'reference_at': now.isoformat(), 'policy': policy,
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
        main, detail = master_public_copy(selected, 'single_main_v5' if selected.get('writer_review', {}).get('v5') else policy.get('publication_style'), now=now)
        checked.append({'scheduled_at': entry['scheduled_at'], 'notice_id': entry['notice_id'],
                        'format_id': entry['format_id'], 'chars': len(entry['writer']['post_text']),
                        'public_preview': {'main_text': main, 'detail_reply': detail},
                        'editorial_policy_id': entry.get('editorial_policy_id')})
    return {'status': 'validated', 'ready_entries': checked}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=24)
    parser.add_argument('--check-queue', help='Validate upcoming ready drafts without sending')
    parser.add_argument('--queue-for-selection', help='Fresh remote queue JSON; exclude notices already prepared for an active or future slot')
    parser.add_argument('--reviews-for-selection', help='Independent official review JSON (same schema); validate evidence without reserving notices')
    args = parser.parse_args()
    if not 1 <= args.limit <= 60:
        parser.error('limit must be 1 to 60')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    def selection_entries(path):
        if path is None:
            return None
        snapshot = json.loads(Path(path).read_text(encoding='utf-8'))
        if snapshot.get('schema_version') != 1 or not isinstance(snapshot.get('entries'), list):
            raise ValueError('Invalid selection input queue schema')
        return snapshot['entries']

    output = (check_queue(args.check_queue, now) if args.check_queue
              else build_input(now, args.limit, selection_entries(args.reviews_for_selection),
                               queued_entries=selection_entries(args.queue_for_selection)))
    print(json.dumps(output, ensure_ascii=False, indent=2))
