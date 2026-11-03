"""Read every page in a declared recent GOJOBS window; never replace site data."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import re
import html
import urllib.request
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gojobs
from gojobs_notice_safety import classify_notice

PAGE_SIZE = 100
MAX_PAGES = 10
DETAIL_LIMIT = 8
KST = timezone(timedelta(hours=9))


def body_application_period(text):
    """Read an explicitly labelled date range only; never use exam/result dates."""
    match=re.search(r'(?:원서)?접수(?:기간)?\s*[:：]\s*(.{0,180})', text)
    if not match:
        return None
    found=re.search(r'(20\d{2})[.년/-]\s*(\d{1,2})[.월/-]\s*(\d{1,2})[.일]?(?:\s*\([^)]{1,5}\))?\s*[~∼～–—]\s*(?:(20\d{2})[.년/-]\s*)?(\d{1,2})[.월/-]\s*(\d{1,2})[.일]?',match[1])
    if not found:
        return None
    y,m,d,y2,m2,d2=found.groups()
    try:
        return (gojobs._date(f'{y}-{int(m):02d}-{int(d):02d}'),
                gojobs._date(f'{y2 or y}-{int(m2):02d}-{int(d2):02d}'))
    except gojobs.APIError:
        raise gojobs.APIError('body_application_dates_invalid') from None


def official_page(row, *, opener=urllib.request.urlopen):
    """Verify one derived public URL against its visible table, not its API enddate."""
    url = 'https://www.gojobs.go.kr/apmView.do?empmnsn=' + row['id']
    with opener(url, timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise gojobs.APIError('official_page_redirect_or_status')
        raw = response.read(2_000_001)
    if len(raw)>2_000_000:
        raise gojobs.APIError('official_page_too_large')
    source = raw.decode('utf-8')
    def plain(value):
        return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]*>', ' ', value))).strip()
    def cell(label):
        found = re.findall(r'<th\b[^>]*>\s*'+re.escape(label)+r'\s*</th>\s*<td\b[^>]*>(.*?)</td>',source,re.S)
        if len(found)!=1:
            raise gojobs.APIError('official_field_missing_or_duplicate')
        return plain(found[0])
    title, org = cell('공고명'), cell('기관명')
    normalize=lambda value: re.sub(r'\s+', '', value)
    if normalize(title)!=normalize(row['title']) or normalize(org)!=normalize(row['org']):
        raise gojobs.APIError('official_identity_mismatch')
    start, end = gojobs._date(cell('접수시작일')), gojobs._date(cell('접수마감일'))
    if not start or not end or start>end:
        raise gojobs.APIError('official_application_dates_invalid')
    content=re.findall(r'<textarea\b[^>]*\bid="content"[^>]*>(.*?)</textarea>',source,re.S)
    if len(content)!=1 or not plain(content[0]):
        raise gojobs.APIError('official_content_missing')
    body_period=body_application_period(plain(content[0]))
    if body_period and body_period!=(start,end):
        raise gojobs.APIError('official_table_body_period_conflict')
    return {'id':'gojobs-'+row['id'], 'source_id':row['id'], 'source':'나라일터',
        'title':title,'org':org,'url':url,'application_start':start,'application_end':end,
        'content':plain(content[0]),'region':cell('근무지역'),
        'source_sha256':hashlib.sha256(raw).hexdigest()}


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
    details, official = [], []
    # Titles only select records for inspection; never establish availability.
    candidates = [row for row in rows if row['triage']['reason']=='official_source_unverified'
                  and row['deadline'] and row['deadline']>=end]
    candidates.sort(key=lambda row: (row['deadline'], row['registered_date'], int(row['id'])))
    for row in candidates[:DETAIL_LIMIT]:
        detail = client.detail(row['id'])
        if any(detail[field] != row[field] for field in
               ('id', 'title', 'institution_type', 'recruitment_type')):
            raise gojobs.APIError('detail_list_mismatch')
        details.append(detail)
        # The page must independently match the API identity and its application
        # period. A result/registration title still cannot become recruitment.
        try:
            record=official_page(row)
            record['classification']=classify_notice(row['title'],official_text=record['content'],
                official_verified=True,application_open_verified=record['application_start']<=end<=record['application_end'],as_of=end,deadline=row['deadline'])
            record['application_state']='접수예정' if record['application_start']>end else '접수마감' if record['application_end']<end else '모집중'
            official.append(record)
        except gojobs.APIError as error:
            official.append({'id':'gojobs-'+row['id'],'verification_error':error.safe_code})
        except Exception:
            official.append({'id':'gojobs-'+row['id'],'verification_error':'official_page_unavailable'})
    return {'window': {'start': start, 'end': end, 'field': 'registered_date'},
        'scope': 'g02/e01,e02 only; bounded recent registration window, not full history',
        'complete_window': True, 'total_by_filter': totals, 'records': rows,
        'detail_samples': details, 'requests': client.request_counts,
        'official_page_samples': official,
        'successful_responses': client.success_counts,
        'eligible_for_publication': sum(p.get('classification',{}).get('recruiting') is True for p in official), 'official_application_period_verified': any('application_start' in p for p in official),
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
