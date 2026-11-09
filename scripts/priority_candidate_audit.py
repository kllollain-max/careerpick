"""Read-only ALIO editorial shortlist; does not claim measured search popularity."""
import argparse
import json
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit

def as_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None

def seat_count(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value if 1 <= value <= 5000 else None
    if isinstance(value, str) and re.fullmatch(r'\d{1,4}', value.strip()):
        count = int(value.strip())
        return count if 1 <= count <= 5000 else None
    return None

def shortlist(feed, today, limit=30):
    if not isinstance(feed, dict) or not isinstance(feed.get('posts'), list):
        raise ValueError('invalid_feed')
    if not isinstance(today, date) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('invalid_arguments')
    selected, rejected, seen = [], {}, set()
    for p in feed['posts']:
        if not isinstance(p, dict):
            rejected['malformed'] = rejected.get('malformed', 0) + 1
            continue
        identity, title = p.get('id'), p.get('title')
        end = as_date(p.get('due'))
        url = p.get('url', '')
        emp = p.get('emp') if isinstance(p.get('emp'), list) else []
        if not isinstance(identity, str) or not re.fullmatch(r'a\d+', identity) or identity in seen:
            reason = 'duplicate_or_bad_id'
        elif not isinstance(title, str) or not title.strip():
            reason = 'missing_title'
        elif not end:
            reason = 'unknown_deadline'
        elif end < today:
            reason = 'expired'
        elif not isinstance(url, str) or urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'job.alio.go.kr':
            reason = 'unverified_source'
        else:
            reason = None
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        seen.add(identity)
        seats = seat_count(p.get('n'))
        permanent = any(isinstance(x, str) and ('정규직' in x and '비정규직' not in x) for x in emp)
        # Score is editorial triage only, NOT search demand, application eligibility or popularity.
        score = (100 if permanent else 0) + (min(seats, 100) if seats is not None else 0)
        selected.append({'id': identity, 'title': title.strip(), 'organization': str(p.get('org', '')),
                         'due': end.isoformat(), 'employment': emp, 'reported_seats': seats,
                         'permanent_classified': permanent, 'triage_score': score, 'official_url': url})
    selected.sort(key=lambda x: (-x['triage_score'], x['due'], x['id']))
    return {'as_of': today.isoformat(), 'source': 'ALIO existing validated feed', 'source_rows': len(feed['posts']),
            'eligible_rows': len(selected), 'excluded': rejected, 'top': selected[:limit],
            'limitations': ['Not a search-volume or actual popularity ranking',
                            'Reported hiring counts are source fields, not independently confirmed headcount',
                            'Application requirements and current status must be reviewed at the official page',
                            'Unknown and expired deadlines are never promoted']}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='alio.json')
    parser.add_argument('--output', default='review-only/job-priority-candidates.json')
    parser.add_argument('--as-of', default=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
    args = parser.parse_args()
    report = shortlist(json.loads(Path(args.source).read_text(encoding='utf-8')), date.fromisoformat(args.as_of))
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'source_rows': report['source_rows'], 'eligible_rows': report['eligible_rows'],
                      'top_rows': len(report['top']), 'excluded': report['excluded']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
