#!/usr/bin/env python3
"""Source-checked Threads review staging -> SHA/CAS publisher queue bridge.

Never generates unverified facts, grants approval, or calls Meta POST.
Uses the actual publisher validator and verifies the original image asset.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.threads_auto import writer_inputs, load, master_public_copy
from scripts.threads_writer_queue import fingerprint, validate_entry
from scripts.threads_candidate_selection import build_selection
from scripts.threads_v5 import STYLE as V5_STYLE

KST = ZoneInfo('Asia/Seoul')
HOURS = (8, 12, 16, 20)
BRANCH = 'threads-publisher-state'
QUEUE = 'threads/writer-queue.json'
STAGING = 'threads/reviewed-staging.json'


def future_slots(now):
    result = []
    for day in range(3):
        date = (now + timedelta(days=day)).date()
        for hour in HOURS:
            slot = datetime.combine(date, datetime.min.time(), tzinfo=KST).replace(hour=hour)
            if now < slot <= now + timedelta(hours=25):
                result.append(slot.isoformat())
    return result


def next_media(history):
    recent = next((r for r in reversed(history.get('records', []))
                   if r.get('status') == 'published' and r.get('threads_post_id')
                   and 'image_url' in r), None)
    return 'IMAGE' if recent is not None and not recent.get('image_url') else 'TEXT'


def eligible_staged_slot(entry, now):
    """Keep the publisher's existing 2h grace only for pre-slot reviewed entries."""
    supplied = entry.get('scheduled_at')
    if supplied in future_slots(now):
        return True
    try:
        slot = datetime.fromisoformat(supplied)
        prepared = datetime.fromisoformat(entry['prepared_at'])
        if slot.utcoffset() is None or prepared.utcoffset() is None:
            return False
        local = slot.astimezone(KST)
        return (local.hour in HOURS and local.minute == local.second == local.microsecond == 0
                and timedelta(0) <= now-slot < timedelta(hours=2)
                and prepared < slot)
    except (KeyError, TypeError, ValueError):
        return False


def verify_entry(entry, now, history, policy, source, details):
    if not isinstance(entry, dict) or not isinstance(entry.get('writer'), dict):
        raise ValueError('STAGED_ENTRY_SCHEMA')
    if entry['writer'].get('status') != 'ready':
        raise ValueError('STAGED_NOT_READY')
    if not eligible_staged_slot(entry, now):
        raise ValueError('STAGED_SLOT_EXPIRED_OR_FUTURE')
    selected = validate_entry(entry, datetime.fromisoformat(entry['scheduled_at']),
                              now, history, source, details, policy)
    if not selected.get('writer_review', {}).get('v5'):
        raise ValueError('V5_REVIEW_REQUIRED')
    text, reply = master_public_copy(selected, V5_STYLE, now=now)
    if reply or text != entry['writer'].get('post_text'):
        raise ValueError('PUBLIC_TEXT_MISMATCH')
    if next_media(history) == 'IMAGE':
        from scripts.threads_card_review import verify_reviewed_card
        verify_reviewed_card(selected['image_job'], selected['writer_review'],
                             ROOT, now, verify_pixels=False)
    return selected


def merge(queue, staged, history, policy, source, details, now, claimed_slots=()):
    if queue.get('schema_version') != 1 or not isinstance(queue.get('entries'), list):
        raise ValueError('QUEUE_SCHEMA')
    if staged.get('schema_version') != 1 or not isinstance(staged.get('entries'), list):
        raise ValueError('STAGING_SCHEMA')
    blocked = set(map(str, history.get('posted_ids', [])))
    for r in history.get('records', []):
        if r.get('job_id'):
            blocked.add(str(r['job_id']))
        blocked.update(str(x) for x in r.get('job_ids', []) if x)
    occupied = {x.get('scheduled_at') for x in queue['entries']}
    used = {x.get('notice_id') for x in queue['entries']
            if isinstance(x.get('writer'), dict) and x['writer'].get('status') == 'ready'}
    approved, refused = [], []
    for entry in staged['entries']:
        nid = entry.get('notice_id') if isinstance(entry, dict) else None
        try:
            if not isinstance(nid, str) or nid in blocked:
                raise ValueError('DUPLICATE_POST')
            if entry.get('scheduled_at') in occupied:
                raise ValueError('SLOT_ALREADY_OCCUPIED')
            if entry.get('scheduled_at') in claimed_slots:
                raise ValueError('SLOT_ALREADY_CLAIMED')
            if any(r.get('scheduled_at') == entry.get('scheduled_at') for r in history.get('records', [])):
                raise ValueError('SLOT_ALREADY_STARTED')
            if nid in used:
                raise ValueError('DUPLICATE_QUEUE_NOTICE')
            verify_entry(entry, now, history, policy, source, details)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            refused.append({'notice_id': nid, 'reason': str(exc)[:140]})
            continue
        approved.append(entry)
        occupied.add(entry['scheduled_at'])
        used.add(nid)
    return {**queue, 'entries': [*queue['entries'], *approved]}, approved, refused


def ready_future_slots(entries, now):
    """Only approved, ready drafts occupy a future publishing slot."""
    ready = {entry.get('scheduled_at') for entry in entries
             if isinstance(entry, dict) and isinstance(entry.get('writer'), dict)
             and entry['writer'].get('status') == 'ready'}
    return [slot for slot in future_slots(now) if slot in ready]


def supply_status(entries, now):
    """Classify immediate versus later missing slots without approving drafts."""
    slots = future_slots(now)
    approved = set(ready_future_slots(entries, now))
    missing = [slot for slot in slots if slot not in approved]
    return {'future_slots': slots, 'approved_future_slots': [slot for slot in slots if slot in approved],
            'missing_slots': missing, 'next_slot_missing': bool(slots and slots[0] in missing)}


def request(method, path, token, payload=None):
    repo = os.environ['GITHUB_REPOSITORY']
    url = 'https://api.github.com/repos/' + repo + '/contents/' + path
    if method == 'GET':
        url += '?ref=' + urllib.parse.quote(BRANCH)
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, method=method, data=data, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def read(path, token):
    result = request('GET', path, token)
    return json.loads(base64.b64decode(result['content']).decode()), result['sha']


def run(apply=False):
    now = datetime.now(KST)
    token = os.environ.get('THREADS_CLAIM_TOKEN')
    if not token or not os.environ.get('GITHUB_REPOSITORY'):
        raise RuntimeError('GITHUB_CLAIM_ACCESS_REQUIRED')
    history = load(ROOT / 'threads_posted.json', {'records': [], 'posted_ids': []})
    policy, source, details = writer_inputs(ROOT)
    report = {'time': now.isoformat(), 'future_slots': future_slots(now),
              'next_media': next_media(history), 'promoted': [], 'refused': [],
              'queue_updated': False, 'meta_posted': False}
    for attempt in range(3):
        queue, sha = read(QUEUE, token)
        try:
            staged, stage_sha = read(STAGING, token)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            staged, stage_sha = {'schema_version': 1, 'entries': []}, None
        claimed_slots = set()
        for entry in staged.get('entries', []):
            if not isinstance(entry, dict) or not eligible_staged_slot(entry, now):
                continue
            slot = datetime.fromisoformat(entry['scheduled_at'])
            if slot <= now:
                name = slot.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%MZ.json')
                try:
                    request('GET', 'threads-claims/' + name, token)
                    claimed_slots.add(entry['scheduled_at'])
                except urllib.error.HTTPError as exc:
                    if exc.code != 404:
                        raise
        merged, approved, refused = merge(queue, staged, history, policy, source, details, now, claimed_slots)
        selection = build_selection(source, details, history, policy, now, 24,
                                    queued_entries=merged['entries'])
        readiness = supply_status(merged['entries'], now)
        # A queued 'ready' flag alone does not prove a publishable entry.
        # Revalidate future reservations against current official snapshots.
        valid_slots, invalid_ready = [], []
        for entry in merged['entries']:
            if not isinstance(entry, dict) or entry.get('scheduled_at') not in readiness['future_slots']:
                continue
            if not isinstance(entry.get('writer'), dict) or entry['writer'].get('status') != 'ready':
                continue
            try:
                verify_entry(entry, now, history, policy, source, details)
                valid_slots.append(entry['scheduled_at'])
            except (ValueError, KeyError, TypeError, RuntimeError) as exc:
                invalid_ready.append({'notice_id': entry.get('notice_id'),
                                      'slot': entry.get('scheduled_at'), 'reason': str(exc)[:140]})
        approved_slots = [slot for slot in readiness['future_slots'] if slot in valid_slots]
        readiness['approved_future_slots'] = approved_slots
        readiness['missing_slots'] = [slot for slot in readiness['future_slots'] if slot not in approved_slots]
        readiness['next_slot_missing'] = bool(readiness['future_slots'] and readiness['future_slots'][0] not in approved_slots)
        report.update(queue_sha=sha, staged_sha=stage_sha,
                      approved_supply_count=len(approved),
                      invalid_ready_entries=invalid_ready,
                      approved_future_slots=approved_slots,
                      missing_slots=readiness['missing_slots'],
                      next_slot_missing=readiness['next_slot_missing'],
                      source_candidate_count=len(selection.get('candidates', [])),
                      writer_handoff={'status': 'review_required',
                                      'missing_slots': [slot for slot in future_slots(now)
                                                        if slot not in approved_slots],
                                      'candidate_notice_ids': [item.get('notice_id')
                                                               for item in selection.get('candidates', [])[:24]],
                                      'candidates': [{'notice_id': item.get('notice_id'),
                                                      'org': item.get('source_post', {}).get('org'),
                                                      'title': item.get('source_post', {}).get('title'),
                                                      'official_url': item.get('source_post', {}).get('src') or item.get('source_post', {}).get('url'),
                                                      'employment': item.get('selection_context', {}).get('employment'),
                                                      'application_period': item.get('selection_context', {}).get('application_period'),
                                                      'source_post_sha256': item.get('source_post_sha256'),
                                                      'source_detail_sha256': item.get('source_detail_sha256'),
                                                      'review_status': 'official_review_required',
                                                      'application_evidence': item.get('selection_context', {}).get('application_period', {}).get('evidence') if isinstance(item.get('selection_context', {}).get('application_period'), dict) else None,
                                                      'application_source_ref': item.get('selection_context', {}).get('application_period', {}).get('source_ref') if isinstance(item.get('selection_context', {}).get('application_period'), dict) else None,
                                                      'source_snapshot_checked_at': source.get('_operations', {}).get('last_success_at') if isinstance(source.get('_operations'), dict) else None}
                                                     for item in selection.get('candidates', [])[:24]],
                                      'automatic_approval': False,
                                      'meta_posted': False},
                      shortlisted=[{'notice_id': e.get('notice_id'),
                                    'org': e.get('source_post', {}).get('org'),
                                    'title': e.get('source_post', {}).get('title'),
                                    'employment': e.get('selection_context', {}).get('employment'),
                                    'application_period': e.get('selection_context', {}).get('application_period')}
                                   for e in selection.get('candidates', [])[:12]],
                      promoted=[{'notice_id': e['notice_id'], 'slot': e['scheduled_at'],
                                 'fingerprint': fingerprint(e)} for e in approved],
                      refused=refused)
        if not apply or not approved:
            break
        raw = json.dumps(merged, ensure_ascii=False, indent=2) + '\n'
        try:
            request('PUT', QUEUE, token, {
                'sha': sha, 'branch': BRANCH,
                'message': 'Promote reviewed CareerPick Threads draft [skip ci]',
                'content': base64.b64encode(raw.encode()).decode()})
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 422) and attempt < 2:
                time.sleep(1)
                continue
            raise
        verified, new_sha = read(QUEUE, token)
        if verified != merged:
            raise RuntimeError('QUEUE_READBACK_MISMATCH')
        report['queue_updated'] = True
        report['queue_sha_after'] = new_sha
        break
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--output', default='threads-queue-preflight.json')
    args = parser.parse_args()
    report = run(args.apply)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
