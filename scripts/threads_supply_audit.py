"""Persist source-backed writer handoff and report missed slots; never publish.

A durable CAS handoff enables the independent writer to resume after an Actions
runner exits. It never fabricates editorial approval or refreshes review clocks.
"""
import argparse
import base64
import hashlib
import json
import os
import time
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.threads_queue_bridge import BRANCH, HOURS, read, request

KST = ZoneInfo('Asia/Seoul')
STATE_PATH = 'threads/replenishment-handoff.json'


def audit_slots(history, now):
    if now.utcoffset() is None:
        raise ValueError('NOW_TIMEZONE')
    now = now.astimezone(KST)
    rows = history.get('records')
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('HISTORY_SCHEMA')
    slots = []
    # Observe the prior 48h, allowing two hours for a delayed scheduled runner.
    for back in (2, 1, 0):
        day = (now - timedelta(days=back)).date()
        for hour in HOURS:
            slot = datetime.combine(day, datetime.min.time(), KST).replace(hour=hour)
            if not now - timedelta(hours=48) <= slot <= now - timedelta(hours=2):
                continue
            matches = []
            for record in rows:
                if record.get('test_only') or record.get('dry_run'):
                    continue
                try:
                    stamp = datetime.fromisoformat(record['scheduled_at'])
                    if stamp.utcoffset() is None:
                        continue
                    if stamp == slot:
                        matches.append(record)
                except (KeyError, TypeError, ValueError):
                    continue
            ids = sorted({str(r['threads_post_id']) for r in matches
                          if r.get('status') == 'published' and r.get('threads_post_id')})
            slots.append({'scheduled_at': slot.isoformat(), 'post_ids': ids,
                          'status': 'duplicate_receipts' if len(ids) > 1 else
                          'recorded_publication' if ids else
                          'unresolved_pending' if any(r.get('status') == 'pending' for r in matches) else
                          'missing_receipt'})
    recorded = sum(s['status'] == 'recorded_publication' for s in slots)
    return {'slots': slots, 'expected_slots': len(slots), 'recorded_publications': recorded,
            'receipt_success_rate': recorded / len(slots) if slots else None,
            'live_meta_verification_performed': False,
            'needs_attention': [s for s in slots if s['status'] != 'recorded_publication']}


def build_handoff(preflight, handoff, drafts, evidence, history, now, live_inventory=None):
    if (handoff.get('automatic_approval') is not False or handoff.get('meta_posted') is not False
            or drafts.get('approved_for_queue') is not False
            or evidence.get('approved_for_queue') is not False):
        raise ValueError('UNSAFE_HANDOFF')
    return {'schema_version': 1, 'captured_at': now.isoformat(),
            'run_id': os.environ.get('GITHUB_RUN_ID'),
            'source_commit': os.environ.get('GITHUB_SHA'),
            'status': 'independent_review_required', 'automatic_approval': False,
            'meta_posted': False, 'preflight': preflight, 'writer_handoff': handoff,
            'unreviewed_drafts': drafts, 'official_evidence': evidence,
            'publication_audit': audit_slots(history, now),
            'live_inventory': live_inventory}


def persist_handoff(bundle, token, reader=read, writer=request, sleeper=time.sleep):
    raw = json.dumps(bundle, ensure_ascii=False, indent=2) + '\n'
    for attempt in range(3):
        try:
            current, sha = reader(STATE_PATH, token)
            old = datetime.fromisoformat(current['captured_at'])
            new = datetime.fromisoformat(bundle['captured_at'])
            if old.utcoffset() is None or new.utcoffset() is None:
                raise ValueError('HANDOFF_TIMEZONE')
            if old > new:
                raise ValueError('NEWER_HANDOFF_ALREADY_EXISTS')
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            sha = None
        payload = {'branch': BRANCH, 'message': 'Preserve Threads replenishment evidence [skip ci]',
                   'content': base64.b64encode(raw.encode()).decode()}
        if sha:
            payload['sha'] = sha
        try:
            writer('PUT', STATE_PATH, token, payload)
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 422) and attempt < 2:
                sleeper(2 ** attempt)
                continue
            raise
        verified, _ = reader(STATE_PATH, token)
        if verified != bundle:
            raise RuntimeError('HANDOFF_READBACK_MISMATCH')
        return hashlib.sha256(raw.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--persist', action='store_true')
    args = parser.parse_args()
    def load(name):
        return json.loads(Path(name).read_text(encoding='utf-8'))
    bundle = build_handoff(load('threads-queue-preflight.json'), load('threads-writer-handoff.json'),
                           load('threads-unreviewed-drafts.json'), load('threads-official-evidence.json'),
                           load('threads_posted.json'), datetime.now(KST),
                           load('threads-live-inventory.json'))
    result = {'persisted': False, 'meta_posted': False,
              'publication_audit': bundle['publication_audit']}
    if args.persist:
        if os.environ.get('GITHUB_REPOSITORY') != 'kllollain-max/careerpick':
            raise ValueError('WRONG_REPOSITORY')
        result.update(persisted=True, sha256=persist_handoff(bundle, os.environ['THREADS_CLAIM_TOKEN']))
    Path('threads-supply-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
