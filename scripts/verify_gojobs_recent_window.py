"""Read every page in a declared recent GOJOBS window; never replace site data."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gojobs
from gojobs_notice_safety import classify_notice

PAGE_SIZE = 100
MAX_PAGES = 10
DETAIL_LIMIT = 8
KST = timezone(timedelta(hours=9))


def collect_window(client, start, end):
    """Reject ignored date filters, changing totals and incomplete pagination."""
    rows, totals, seen = [], {}, set()
    for category in ('e01', 'e02'):
        page, total = 1, None
        while True:
            body = client._request('list', {'pageNo': page, 'numOfRows': PAGE_SIZE,
                'Pblanc_ty': category, 'Instt_se': 'g02', 'Sort_order': '1',
                'Begin_de': start, 'End_de': end})
            actual_total = gojobs._integer(gojobs._text(body, 'totalCount', required=True))
            if total is None:
                total = actual_total
                if math.ceil(total / PAGE_SIZE) > MAX_PAGES:
                    raise gojobs.APIError('window_page_limit')
            if actual_total != total:
                raise gojobs.APIError('pagination_changed')
            if (gojobs._integer(gojobs._text(body, 'pageNo', required=True)) != page
                    or gojobs._integer(gojobs._text(body, 'numOfRows', required=True)) != PAGE_SIZE
                    or len(body.findall('items')) > 1):
                raise gojobs.APIError('pagination_mismatch')
            items = body.findall('items/item')
            if len(items) != min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE)):
                raise gojobs.APIError('partial_page')
            for item in items:
                identity = str(gojobs._integer(gojobs._text(item, 'idx', required=True), positive=True))
                if identity in seen:
                    raise gojobs.APIError('duplicate_identifier')
                seen.add(identity)
                institution, recruitment, layout = client._classifications(item, category)
                registered = gojobs._date(gojobs._text(item, 'regdate', required=True, limit=20))
                if not start <= registered <= end:
                    raise gojobs.APIError('date_filter_not_honored')
                row = {'id': identity, 'title': gojobs._text(item, 'title', required=True),
                    'org': gojobs._text(item, 'insttname', required=True),
                    'registered_date': registered,
                    'deadline': gojobs._date(gojobs._text(item, 'enddate', limit=20)),
                    'institution_type': institution, 'recruitment_type': recruitment,
                    'field_layout': layout}
                client._reject_credential_echo(row)
                row['triage'] = classify_notice(row['title'], as_of=end, deadline=row['deadline'])
                rows.append(row)
            client.success_counts['list'] += 1
            if page * PAGE_SIZE >= total:
                totals[category] = {'records': total, 'pages': page}
                break
            page += 1
    details = []
    # Titles only select records for inspection; never establish availability.
    candidates = [row for row in rows if row['triage']['category'] == '상태 미확인']
    candidates.sort(key=lambda row: (row['registered_date'], int(row['id'])), reverse=True)
    for row in candidates[:DETAIL_LIMIT]:
        detail = client.detail(row['id'])
        if any(detail[field] != row[field] for field in
               ('id', 'title', 'institution_type', 'recruitment_type')):
            raise gojobs.APIError('detail_list_mismatch')
        details.append(detail)
    return {'window': {'start': start, 'end': end, 'field': 'registered_date'},
        'scope': 'g02/e01,e02 only; bounded recent registration window, not full history',
        'complete_window': True, 'total_by_filter': totals, 'records': rows,
        'detail_samples': details, 'requests': client.request_counts,
        'successful_responses': client.success_counts,
        'eligible_for_publication': 0, 'official_application_period_verified': False,
        'production_data_writes': 0}


def main():
    now = datetime.now(KST)
    paths = ('alio.json', 'alio-detail.json')
    before = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in paths}
    output = Path('gojobs-window-output')
    output.mkdir(exist_ok=True)
    report = {'started_at': now.isoformat(timespec='seconds'), 'status': 'failed',
              'production_data_writes': 0}
    client = None
    try:
        client = gojobs.Client(os.environ.get('GOJOBS_KEY', ''))
        report.update(collect_window(client, (now.date()-timedelta(days=14)).isoformat(), now.date().isoformat()))
        report['status'] = 'verified_recent_window'
    except gojobs.APIError as error:
        report['error'] = error.safe_code
    except Exception:
        report['error'] = 'unexpected_verification_failure'
    report['finished_at'] = datetime.now(KST).isoformat(timespec='seconds')
    report['originals_preserved'] = all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest for name,digest in before.items())
    if client:
        report['requests'] = client.request_counts
        report['authentication_verified'] = client.success_counts['list'] > 0
        client._reject_credential_echo(report)
    if not report['originals_preserved']:
        report['status'] = 'failed'
        report['error'] = 'original_changed'
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status']=='verified_recent_window' else 1


if __name__ == '__main__':
    raise SystemExit(main())
