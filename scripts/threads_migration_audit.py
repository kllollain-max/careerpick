"""Read-only account/post audit. Does not modify history or enable publishing."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.threads_auto import api, verify_account


def collect(call):
    posts, after, complete = {}, None, False
    for _ in range(10):
        params = {'fields': 'id,text,timestamp', 'limit': 100}
        if after:
            params['after'] = after
        result = call('GET', '/me/threads', params)
        for post in result.get('data', []):
            if str(post.get('id', '')).isdigit():
                posts[str(post['id'])] = post
        paging = result.get('paging') or {}
        if not paging.get('next'):
            complete = True
            break
        cursor = (paging.get('cursors') or {}).get('after')
        if not cursor or cursor == after:
            break
        after = cursor
    return list(posts.values()), complete


def main():
    token = os.environ.get('THREADS_ACCESS_TOKEN', '')
    if not token:
        raise SystemExit('THREADS_ACCESS_TOKEN is required; no request made')
    account = verify_account(token, os.environ.get('THREADS_USER_ID', ''))
    posts, complete = collect(lambda method, path, params: api(method, path, token, params))
    history = json.loads(Path('threads_posted.json').read_text())
    known = {str(r['threads_post_id']) for r in history['records'] if r.get('threads_post_id')}
    # These IDs are prior verified evidence, not invented history or new receipts.
    expected = ['18029250455877919', '17909910720593443', '18132626512765431']
    evidence = [api('GET', '/' + post_id, token, {'fields': 'id,text,timestamp,media_type,is_reply,root_post,replied_to'}) for post_id in expected]
    extra = [api('GET', '/18120384022755046', token, {'fields': 'id,text,timestamp,media_type,permalink'})]
    limits = api('GET', '/me/threads_publishing_limit', token, {'fields': 'quota_usage,config'})
    report = {'extra_objects': extra, 'publishing_limit': limits, 'observed_at': datetime.now(timezone.utc).isoformat(), 'account_id': account,
              'scan_complete': complete, 'posts': posts, 'previously_verified_objects': evidence,
              'not_in_backup_ids': [p['id'] for p in posts if str(p['id']) not in known],
              'migration_ready': False,
              'reason': 'Review missing history, replies/parent connections and original publisher state before enabling'}
    Path('threads-migration-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Read-only scan complete:', complete, 'objects:', len(posts), 'unreconciled:', len(report['not_in_backup_ids']))
    print('No publish, history update, claim creation or activation performed')


if __name__ == '__main__':
    main()
