#!/usr/bin/env python3
"""Recover verified receipts and finalize known pre-send failures; no publishing."""
import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import threads_auto as publisher
from scripts.threads_remote_claim import GitHubClaims, ClaimError


def finalize_unsent(history, run_id):
    """Only the original runner may finalize failure before the claim boundary."""
    matches = [r for r in history.get('records', []) if str(r.get('run_id')) == run_id]
    if len(matches) != 1:
        return False
    record = matches[0]
    if (record.get('content_type') != 'master_job' or record.get('status') != 'pending'
            or record.get('request_status') or record.get('threads_post_id')
            or record.get('api_returned_post_id')):
        return False
    record.update(status='failed', failure_stage='before_remote_claim', safe_no_send=True,
                  failed_at=datetime.now(publisher.KST).isoformat())
    return True


def reconcile_accepted(history, remote, token, verifier=None):
    """A remote accepted ID plus exact live text is necessary for local recovery."""
    verifier = verifier or publisher.verify_published_record
    results = []
    for index, record in enumerate(history.get('records', [])):
        if record.get('content_type') != 'master_job' or record.get('status') != 'pending':
            continue
        trial = copy.deepcopy(history)
        candidate = trial['records'][index]
        try:
            publisher.restore_accepted_receipt(candidate, trial, remote)
            objects = verifier(candidate, token)
        except (ClaimError, RuntimeError, ValueError, KeyError):
            results.append({'run_id': str(record.get('run_id')), 'status': 'hold'})
            continue
        if len(objects) != 1:
            raise RuntimeError('Unexpected recovered object count')
        candidate['reconciled_at'] = datetime.now(publisher.KST).isoformat()
        candidate['verified_permalink'] = objects[0].get('permalink', '')
        record.clear()
        record.update(candidate)
        history['posted_ids'] = trial['posted_ids']
        results.append({'run_id': str(record.get('run_id')), 'status': 'verified_recovered',
                        'post_id': record['threads_post_id']})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finalize-unsent', action='store_true')
    args = parser.parse_args()
    history = publisher.load(publisher.HISTORY, {'posted_ids': [], 'records': []})
    if args.finalize_unsent:
        run_id = os.getenv('GITHUB_RUN_ID', '')
        if not run_id.isdigit() or os.getenv('GITHUB_RUN_ATTEMPT', '1') != '1':
            raise RuntimeError('Original first-attempt runner identity required')
        changed = finalize_unsent(history, run_id)
        if changed:
            publisher.save(history)
        print('Known pre-send failure finalized:', changed)
        return
    pending = [r for r in history['records'] if r.get('content_type') == 'master_job'
               and r.get('status') == 'pending']
    if not pending:
        print('No master-prompt receipts need recovery')
        return
    token = os.getenv('THREADS_ACCESS_TOKEN', '')
    if not token:
        raise RuntimeError('Missing publishing credential for read-only verification')
    publisher.verify_account(token)
    remote = GitHubClaims(os.environ['THREADS_CLAIM_REPO'], os.environ['THREADS_CLAIM_BRANCH'],
                          os.environ['THREADS_CLAIM_TOKEN'])
    results = reconcile_accepted(history, remote, token)
    if any(r['status'] == 'verified_recovered' for r in results):
        publisher.save(history)
    (ROOT / '.threads-recovery-report.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False))
    if any(r['status'] == 'hold' for r in results):
        raise RuntimeError('Unconfirmed receipt remains on hold; no automatic resend')


if __name__ == '__main__':
    main()
