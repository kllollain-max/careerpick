"""Read and preserve recent actual Threads receipts; never publish or authorize retry."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def inventory(api, token, expected_id, now, max_pages=4):
    if now.utcoffset() is None or type(max_pages) is not int or not 1 <= max_pages <= 4:
        raise ValueError('INVENTORY_BOUNDS_INVALID')
    account = api('GET', '/me', token, {'fields': 'id,username'})
    if str(account.get('id')) != str(expected_id) or account.get('username') != 'hid_119':
        raise ValueError('THREADS_ACCOUNT_MISMATCH')
    since = now.astimezone(timezone.utc) - timedelta(hours=48)
    posts, seen_ids, seen_cursors = [], set(), set()
    after = None
    complete = False
    for page in range(max_pages):
        params = {'fields': 'id,text,timestamp,permalink,is_reply', 'limit': 100,
                  'since': int(since.timestamp()), 'until': int(now.timestamp())}
        if after:
            params['after'] = after
        response = api('GET', '/me/threads', token, params)
        data = response.get('data')
        if not isinstance(data, list):
            raise ValueError('INVENTORY_RESPONSE_INVALID')
        for post in data:
            if not isinstance(post, dict) or not str(post.get('id', '')).isdigit():
                raise ValueError('INVENTORY_POST_INVALID')
            stamp = datetime.fromisoformat(str(post.get('timestamp', '')).replace('Z', '+00:00'))
            if stamp.utcoffset() is None:
                raise ValueError('INVENTORY_POST_TIMEZONE')
            if post['id'] in seen_ids or not since <= stamp <= now:
                continue
            text = post.get('text')
            if text is not None and not isinstance(text, str):
                raise ValueError('INVENTORY_TEXT_INVALID')
            permalink = post.get('permalink')
            if not isinstance(permalink, str) or not permalink.startswith(('https://www.threads.net/', 'https://www.threads.com/', 'https://threads.net/', 'https://threads.com/')):
                raise ValueError('INVENTORY_PERMALINK_INVALID')
            posts.append({'post_id': str(post['id']), 'timestamp': stamp.isoformat(),
                          'permalink': permalink, 'is_reply': post.get('is_reply'),
                          'text_available': isinstance(text, str),
                          'text_sha256': hashlib.sha256(text.encode()).hexdigest() if isinstance(text, str) else None})
            seen_ids.add(post['id'])
        paging = response.get('paging') or {}
        if not paging.get('next'):
            complete = True
            break
        cursor = (paging.get('cursors') or {}).get('after')
        if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
            break
        seen_cursors.add(cursor)
        after = cursor
    return {'schema_version': 1, 'checked_at': now.isoformat(),
            'window_start': since.isoformat(), 'account': 'hid_119',
            'pages_read': page + 1, 'pagination_complete': complete, 'posts': posts,
            'meta_posted': False, 'safe_to_republish': False,
            'note': 'Remote GET inventory only. Missing receipts require claim and content reconciliation before any catch-up.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='threads-live-inventory.json')
    args = parser.parse_args()
    from scripts.threads_auto import api, KST
    report = inventory(api, os.environ['THREADS_ACCESS_TOKEN'],
                       os.environ['THREADS_USER_ID'], datetime.now(KST))
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f"Actual Threads receipts read: {len(report['posts'])}; pagination complete: {report['pagination_complete']}; no publication")


if __name__ == '__main__':
    main()
