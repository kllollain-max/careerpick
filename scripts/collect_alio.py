#!/usr/bin/env python3
"""Collect into an isolated staging tree; validate and merge by official ID.

Uses the verified ALIO OpenData collector. No qnet/history/publish calls.
Missing key, incomplete responses or invalid payloads never replace snapshots.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alio
ROOT = Path(__file__).resolve().parents[1]


def collect(root=ROOT):
    if not os.environ.get('ALIO_KEY', '').strip():
        return {'status': 'blocked_missing_secret', 'secret': 'ALIO_KEY', 'changed': False}
    originals = {n: (root / n).read_bytes() for n in ('alio.json', 'alio-detail.json')}
    old = json.loads(originals['alio.json'])
    old_details = json.loads(originals['alio-detail.json'])
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for name, content in originals.items():
            (stage / name).write_bytes(content)
        previous_out, previous_detail = alio.OUT, alio.DETAIL
        try:
            alio.OUT, alio.DETAIL = stage / 'alio.json', stage / 'alio-detail.json'
            response = alio.main()
        finally:
            alio.OUT, alio.DETAIL = previous_out, previous_detail
        if response is None:
            return {'status': 'collection_failed_preserved', 'changed': False}
        new = json.loads((stage / 'alio.json').read_bytes())
        details = json.loads((stage / 'alio-detail.json').read_bytes())
        posts = new.get('posts')
        if not isinstance(posts, list) or not posts or not isinstance(details, dict):
            raise ValueError('Invalid collection payload; existing snapshots preserved')
        ids = []
        for post in posts:
            identity = post.get('id', '')
            if not identity.startswith('a') or not identity[1:].isdigit() or identity not in details:
                raise ValueError('Invalid ID or missing detail; existing snapshots preserved')
            if str(details[identity].get('recrutPblntSn', '')) != identity[1:]:
                raise ValueError('Detail identity mismatch; existing snapshots preserved')
            ids.append(identity)
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate IDs; existing snapshots preserved')
        merged = {p['id']: p for p in old['posts']}
        merged.update({p['id']: p for p in posts})
        new['posts'] = sorted(merged.values(), key=lambda p: (p.get('due') or '9999', p['id']))
        merged_details = {**old_details, **details}
        result = {'status': 'collected', 'changed': False, 'received': len(posts),
                  'received_ids': sorted(ids), 'retained': len(merged), 'new_ids': len(set(ids) - {p['id'] for p in old['posts']})}
        old_posts = sorted(old['posts'], key=lambda p: (p.get('due') or '9999', p['id']))
        if new['posts'] == old_posts and merged_details == old_details:
            # A successful, unchanged fetch must not rewrite source bytes/timestamps or fail CI.
            return result
        # Write candidate pair first. Workflow only uploads both after successful exit.
        candidates = {'alio.json': new, 'alio-detail.json': merged_details}
        try:
            for name, data in candidates.items():
                (root / (name + '.candidate')).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
            for name in candidates:
                os.replace(root / (name + '.candidate'), root / name)
        except Exception:
            for name, content in originals.items():
                (root / name).write_bytes(content)
            raise
        finally:
            for name in candidates:
                (root / (name + '.candidate')).unlink(missing_ok=True)
        result['changed'] = True
        return result


if __name__ == '__main__':
    try:
        result = collect()
        print(json.dumps(result, ensure_ascii=False))
        if result['status'] != 'collected':
            sys.exit(2)
    except Exception as error:
        # Do not print exception messages or response bodies containing key-bearing URLs.
        print(json.dumps({'status': 'failed_preserved', 'error_type': type(error).__name__}))
        sys.exit(1)

