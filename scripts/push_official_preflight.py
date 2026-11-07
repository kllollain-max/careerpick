"""Bounded official detail recheck immediately before push; never sends.

This checks ALIO's published status, not undisclosed employer amendments.
Unknown/network failures defer a task instead of claiming cancellation.
"""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from scripts.detect_new_job_alerts import parse_due, KST

MAX_BYTES = 1024 * 1024
CANCEL_TERMS = ('채용취소', '공고취소', '채용중단')


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = Text()
    parser.feed(value)
    return re.sub(r'\s+', ' ', html.unescape(' '.join(parser.parts))).strip()


def compact(value):
    return re.sub(r'\s+', '', str(value))


class ALIORedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if parts.scheme != 'https' or parts.hostname != 'job.alio.go.kr':
            raise ValueError('Official source redirected outside ALIO')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_detail(job_id):
    if not re.fullmatch(r'a[0-9]+', str(job_id)):
        raise ValueError('Canonical ALIO ID required')
    url = 'https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=' + job_id[1:]
    with build_opener(ALIORedirect()).open(Request(url), timeout=10) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Official detail exceeds bound')
    return raw.decode('utf-8')


def verify(job, now, *, fetcher=fetch_detail):
    if re.fullmatch(r'cleaneye-[0-9]+', str(job.get('id', ''))):
        from scripts.cleaneye_push_preflight import verify as verify_cleaneye
        return verify_cleaneye(job, now)
    due = parse_due(job.get('due'))
    if due is None or due <= now:
        return {'allowed': False, 'definitive': True, 'reason': 'expired'}
    title = compact(job.get('title', ''))
    if job.get('cancelled') is True or job.get('status') in ('cancelled', 'closed') or any(t in title for t in CANCEL_TERMS):
        return {'allowed': False, 'definitive': True, 'reason': 'cancelled_or_closed'}
    try:
        source = fetcher(job['id'])
        title_match = re.search(r'<div\b[^>]*class=[\"\']tit[\"\'][^>]*>(.*?)</div>', source, re.S | re.I)
        statuses = [plain(x) for x in re.findall(r'<span\b[^>]*class=[\"\'][^\"\']*cate[0-9]+[^\"\']*[\"\'][^>]*>(.*?)</span>', source, re.S | re.I)]
        if not title_match or len(statuses) != 1:
            raise ValueError('Unrecognized official page')
        official_title = compact(plain(title_match.group(1)))
        if any(t in official_title for t in CANCEL_TERMS) or statuses[0] in ('마감', '접수마감', '취소', '채용취소'):
            return {'allowed': False, 'definitive': True, 'reason': 'official_cancelled_or_closed'}
        if statuses[0] != '진행중' or official_title != title:
            raise ValueError('Official identity or open status unverified')
        fields = {}
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', source, re.S | re.I):
            label = re.search(r'<th\b[^>]*>(.*?)</th>', row, re.S | re.I)
            value = re.search(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)
            if label and value:
                fields[compact(plain(label.group(1)))] = plain(value.group(1))
        dates = re.findall(r'(?<!\d)(?:20)?\d{2}\.\d{2}\.\d{2}(?!\d)', fields.get('공고기간', ''))
        if len(dates) != 2:
            raise ValueError('Official deadline unavailable')
        end = dates[-1] if len(dates[-1].split('.')[0]) == 4 else '20' + dates[-1]
        if end.replace('.', '-') != due.astimezone(KST).date().isoformat() or compact(fields.get('기관명', '')) != compact(job.get('org', '')):
            raise ValueError('Official agency/deadline differs; refresh required')
        return {'allowed': True, 'definitive': True, 'reason': 'alio_open_verified'}
    except Exception:
        return {'allowed': False, 'definitive': False, 'reason': 'official_unverified'}

