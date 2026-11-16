#!/usr/bin/env python3
"""Source-checked Threads review staging -> SHA/CAS publisher queue bridge.

Never generates unverified facts, grants approval, or calls Meta POST.
Uses the actual publisher validator and verifies the original image asset.
"""
import argparse
import base64
import hashlib
import json
import os
import re
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
SUPPLY_TARGET = 8
BRANCH = 'threads-publisher-state'
QUEUE = 'threads/writer-queue.json'
STAGING = 'threads/reviewed-staging.json'


def official_notice_url(post):
    """Review the official notice, keeping its separate application URL private.

    ALIO src commonly points at an HTTP recruitment vendor. That URL is not
    the canonical institutional notice allowed by the evidence reader.
    """
    url = post.get('url')
    if isinstance(url, str):
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ''
        if parsed.scheme == 'https' and not parsed.username and not parsed.password:
            if host == 'job.alio.go.kr' or host == 'job.cleaneye.go.kr':
                return url
    return None


def review_period(item):
    """Carry exact Cleaneye API date provenance to UNAPPROVED review drafts.

    The API's date-only precision remains date-only. This is not a receipt for
    independently read attachments and cannot satisfy v5 final approval.
    """
    context = item.get('selection_context', {})
    period = context.get('application_period')
    if not isinstance(period, dict):
        return period
    if period.get('evidence') and period.get('source_ref'):
        return dict(period)
    if item.get('source') != 'cleaneye':
        return dict(period)
    detail = item.get('source_detail', {})
    nid = item.get('notice_id')
    if not isinstance(nid, str) or not nid.startswith('cleaneye-'):
        return dict(period)
    from scripts.cleaneye_source_adapter import source_date, SourceValidationError
    raw_start, raw_end = detail.get('접수개시일 원문'), detail.get('접수마감일 원문')
    try:
        for key, flag, raw in [('start', 'start_date_only', raw_start), ('end', 'date_only', raw_end)]:
            parsed, has_time = source_date(raw)
            if period.get(flag) is not (not has_time):
                return dict(period)
            expected = parsed.isoformat() if has_time else parsed.date().isoformat()
            if period.get(key) != expected:
                return dict(period)
    except (SourceValidationError, ValueError, TypeError):
        return dict(period)
    return {**period, 'source_ref': 'cleaneye.json#' + nid + '/application_period',
            'evidence': f'접수개시일 원문: {raw_start}; 접수마감일 원문: {raw_end}'}


def future_slots(now):
    """Plan eight slots in KST; validation still enforces 24h freshness.

    Distant drafts require fresh source and semantic review before promotion.
    The planning horizon never makes stale evidence valid.
    """
    if now.utcoffset() is None:
        raise ValueError("NOW_TIMEZONE")
    now = now.astimezone(KST)
    result = []
    for day in range(4):
        date = (now + timedelta(days=day)).date()
        for hour in HOURS:
            slot = datetime.combine(date, datetime.min.time(), tzinfo=KST).replace(hour=hour)
            if now < slot:
                result.append(slot.isoformat())
    return result[:SUPPLY_TARGET]


def next_media(history):
    recent = next((r for r in reversed(history.get('records', []))
                   if r.get('status') == 'published' and r.get('threads_post_id')
                   and 'image_url' in r), None)
    return 'IMAGE' if recent is not None and not recent.get('image_url') else 'TEXT'


def eligible_staged_slot(entry, now):
    """Keep the publisher's existing 2h grace only for pre-slot reviewed entries."""
    if not isinstance(entry, dict):
        return False
    supplied = entry.get('scheduled_at')
    if supplied in future_slots(now):
        try:
            slot = datetime.fromisoformat(supplied)
            return slot.utcoffset() is not None
        except (TypeError, ValueError):
            return False
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
    if any(not isinstance(entry, dict) for entry in staged['entries']):
        raise ValueError('STAGING_ENTRY_SCHEMA')
    if any(not isinstance(entry, dict) for entry in queue['entries']):
        raise ValueError('QUEUE_ENTRY_SCHEMA')
    if not isinstance(history, dict) or not isinstance(history.get('records'), list) or not isinstance(history.get('posted_ids'), list):
        raise ValueError('HISTORY_SCHEMA')
    blocked = set(map(str, history.get('posted_ids', [])))
    for r in history.get('records', []):
        if r.get('job_id'):
            blocked.add(str(r['job_id']))
        blocked.update(str(x) for x in r.get('job_ids', []) if x)
    entries = list(queue['entries'])
    occupied = {x.get('scheduled_at') for x in entries}
    used = {x.get('notice_id') for x in entries
            if isinstance(x.get('writer'), dict) and x['writer'].get('status') == 'ready'}
    approved, refused = [], []
    for entry in staged['entries']:
        nid = entry.get('notice_id') if isinstance(entry, dict) else None
        try:
            if not isinstance(entry, dict) or not isinstance(nid, str) or nid in blocked:
                raise ValueError('DUPLICATE_POST')
            slot = entry.get('scheduled_at')
            if slot in occupied:
                raise ValueError('SLOT_ALREADY_OCCUPIED')
            if slot in claimed_slots:
                raise ValueError('SLOT_ALREADY_CLAIMED')
            if any(r.get('scheduled_at') == slot for r in history.get('records', [])):
                raise ValueError('SLOT_ALREADY_STARTED')
            if nid in used:
                raise ValueError('DUPLICATE_QUEUE_NOTICE')
            verify_entry(entry, now, history, policy, source, details)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            refused.append({'notice_id': nid, 'reason': str(exc)[:140]})
            continue
        approved.append(entry)
        entries.append(entry)
        occupied.add(slot)
        used.add(nid)
    return {**queue, 'entries': entries}, approved, refused


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


def verified_supply_status(entries, now, history, policy, source, details):
    """Only currently validated ready entries count as supplied; no writes."""
    readiness = supply_status(entries, now)
    valid_slots, invalid_ready = set(), []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('scheduled_at') not in readiness['future_slots']:
            continue
        if not isinstance(entry.get('writer'), dict) or entry['writer'].get('status') != 'ready':
            continue
        try:
            verify_entry(entry, now, history, policy, source, details)
            valid_slots.add(entry['scheduled_at'])
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            invalid_ready.append({'notice_id': entry.get('notice_id'),
                                  'slot': entry.get('scheduled_at'), 'reason': str(exc)[:140]})
    approved = [slot for slot in readiness['future_slots'] if slot in valid_slots]
    missing = [slot for slot in readiness['future_slots'] if slot not in valid_slots]
    return {**readiness, 'approved_future_slots': approved, 'missing_slots': missing,
            'next_slot_missing': bool(missing and missing[0] == readiness['future_slots'][0]),
            'approved_inventory_count': len(approved), 'inventory_target': SUPPLY_TARGET,
            'inventory_shortfall': max(0, SUPPLY_TARGET - len(approved)),
            'replenishment_required': len(approved) < SUPPLY_TARGET,
            'invalid_ready_entries': invalid_ready}


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
    # Contents responses omit inline data above 1 MiB. Fetch the immutable
    # blob, never a caller-provided download_url or a moving branch revision.
    sha = result['sha']
    if not result.get('content') and result.get('size', 0) > 0:
        if (not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha)
                or type(result.get('size')) is not int
                or not 0 < result['size'] <= 20_000_000):
            raise ValueError('QUEUE_BLOB_METADATA_INVALID')
        repo = os.environ['GITHUB_REPOSITORY']
        req = urllib.request.Request(
            'https://api.github.com/repos/' + repo + '/git/blobs/' + sha,
            headers={'Authorization': 'Bearer ' + token,
                     'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'})
        with urllib.request.urlopen(req, timeout=25) as response:
            wire = response.read(28_000_001)
        if len(wire) > 28_000_000:
            raise ValueError('QUEUE_BLOB_TOO_LARGE')
        blob = json.loads(wire)
        if (blob.get('sha') != sha or blob.get('size') != result['size']
                or blob.get('encoding') != 'base64'):
            raise ValueError('QUEUE_BLOB_METADATA_MISMATCH')
        raw = base64.b64decode(''.join(blob['content'].split()), validate=True)
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if len(raw) != result['size'] or actual != sha:
            raise ValueError('QUEUE_BLOB_CONTENT_MISMATCH')
    else:
        raw = base64.b64decode(result['content'])
    return json.loads(raw.decode()), sha


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
        selection = build_selection(source, details, history, policy, now, 60,
                                    queued_entries=[*merged['entries'], *staged['entries']])
        for item in selection.get('candidates', []):
            item['selection_context'] = {**item.get('selection_context', {}),
                                         'application_period': review_period(item)}
        readiness = verified_supply_status(merged['entries'], now, history, policy, source, details)
        approved_slots = readiness['approved_future_slots']
        invalid_ready = readiness['invalid_ready_entries']
        report.update(queue_sha=sha, staged_sha=stage_sha,
                      promoted_count=len(approved),
                      approved_supply_count=len(approved_slots),
                      inventory_target=SUPPLY_TARGET,
                      inventory_shortfall=readiness['inventory_shortfall'],
                      replenishment_required=readiness['replenishment_required'],
                      invalid_ready_entries=invalid_ready,
                      approved_future_slots=approved_slots,
                      missing_slots=readiness['missing_slots'],
                      next_slot_missing=readiness['next_slot_missing'],
                      source_candidate_count=len(selection.get('candidates', [])),
                      writer_handoff={'status': 'review_required',
                                      'missing_slots': [slot for slot in future_slots(now)
                                                        if slot not in approved_slots],
                                      'candidate_notice_ids': [item.get('notice_id')
                                                               for item in selection.get('candidates', [])[:100]],
                                      'candidates': [{'notice_id': item.get('notice_id'),
                                                      'org': item.get('source_post', {}).get('org'),
                                                      'title': item.get('source_post', {}).get('title'),
                                                      'official_url': official_notice_url(item.get('source_post', {})),
                                                      'employment': item.get('selection_context', {}).get('employment'),
                                                      'recruiting_unit_title': item.get('selection_context', {}).get('unit_title'),
                                                      'recruiting_unit_count': item.get('selection_context', {}).get('unit_count'),
                                                      'recruiting_unit_scope': item.get('selection_context', {}).get('unit_scope'),
                                                      'selection_review_reasons': item.get('selection_context', {}).get('reasons', []),
                                                      'application_period': item.get('selection_context', {}).get('application_period'),
                                                      'source_post_sha256': item.get('source_post_sha256'),
                                                      'source_detail_sha256': item.get('source_detail_sha256'),
                                                      'official_detail_fields_for_review': {k: v[:1500] for k, v in item.get('source_detail', {}).items() if isinstance(v, str) and k in ('scrnprcdrMthdExpln', 'recrutSe', 'aplyQlfcCn', 'prefCn', 'hireTypeNmLst', 'recrutNope', 'workRgnNmLst', '채용인원', '고용형태 원문', '접수개시일 원문', '접수마감일 원문')},
                                                      'review_status': 'official_review_required',
                                                      'application_evidence': item.get('selection_context', {}).get('application_period', {}).get('evidence') if isinstance(item.get('selection_context', {}).get('application_period'), dict) else None,
                                                      'application_source_ref': item.get('selection_context', {}).get('application_period', {}).get('source_ref') if isinstance(item.get('selection_context', {}).get('application_period'), dict) else None,
                                                      'source_snapshot_checked_at': (source.get('_cleaneye', {}).get('updated') if item.get('source') == 'cleaneye' else source.get('_operations', {}).get('last_success_at'))}
                                                     for item in selection.get('candidates', [])[:100]],
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
