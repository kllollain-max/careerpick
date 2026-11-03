"""Opt-in local Threads insights snapshot ledger; no publishing, no scheduler.

Durability requires a persistent filesystem; GitHub runners are ephemeral.
Use a private durable store before scheduling. The lock is local to a filesystem.
"""
import fcntl
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

WINDOWS = {'24h': timedelta(hours=24), '72h': timedelta(hours=72), '7d': timedelta(days=7)}


def collect_once(path, post_id, published_at, milestone, now, collector):
    if not isinstance(post_id, str) or not post_id.isdigit() or milestone not in WINDOWS:
        raise ValueError('invalid post or milestone')
    if any(not isinstance(x, datetime) or x.tzinfo is None for x in (published_at, now)):
        raise ValueError('timezone-aware times required')
    target = published_at + WINDOWS[milestone]
    if not target <= now <= target + timedelta(hours=12):
        raise ValueError('outside milestone window')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a', encoding='utf-8') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            with path.open(encoding='utf-8') as inp:
                ledger = json.load(inp)
        else:
            ledger = {'version': 1, 'posts': {}}
        if not isinstance(ledger, dict) or ledger.get('version') != 1 or not isinstance(ledger.get('posts'), dict):
            raise ValueError('invalid ledger')
        key = post_id + ':' + milestone
        if key in ledger['posts']:
            return False
        snapshot = collector(post_id)
        if not isinstance(snapshot, dict) or snapshot.get('post_id') != post_id or not isinstance(snapshot.get('metrics'), dict):
            raise ValueError('invalid snapshot')
        if not any(type(v) is int and v >= 0 for v in snapshot['metrics'].values()):
            raise ValueError('no measured metrics; do not consume milestone')
        ledger['posts'][key] = {'post_id': post_id, 'published_at': published_at.isoformat(),
                                'milestone': milestone, 'collected_at': now.isoformat(), 'snapshot': snapshot}
        fd, temp = tempfile.mkstemp(prefix='.threads-snapshot-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                json.dump(ledger, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return True
