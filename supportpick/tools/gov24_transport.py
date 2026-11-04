"""SupportPick Gov24 read-only collector. Stdlib only; never print request URLs."""
import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote, quote
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

BASE = 'https://api.odcloud.kr/api/gov24/v3/'
ENDPOINTS = ('serviceList', 'serviceDetail', 'supportConditions')
SECRET_NAME = 'SUPPORTPICK_GOV24_SERVICE_KEY'
MAX_BYTES = 4 * 1024 * 1024

class APIError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise APIError('redirect_blocked')

def redact(value, key):
    if isinstance(value, dict):
        return {k: redact(v, key) for k, v in value.items() if k.lower() not in ('servicekey', 'authorization')}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        for variant in (key, quote(key, safe=''), quote(quote(key, safe=''), safe='')):
            if variant:
                value = value.replace(variant, '[REDACTED]')
    return value

class Gov24:
    def __init__(self, key, opener=None, sleep=time.sleep):
        self.key = unquote(key.strip())
        if not self.key:
            raise APIError('missing_secret:' + SECRET_NAME)
        if any(c in self.key for c in '\r\n'):
            raise APIError('invalid_key_format')
        self.opener = opener or build_opener(NoRedirect())
        self.sleep = sleep
        self.requests = 0

    def get(self, endpoint, service_id=None, page=1, per_page=1, service_name=None, modified_since=None):
        if endpoint not in ENDPOINTS:
            raise APIError('unsupported_endpoint')
        if not 1 <= page <= 10000 or not 1 <= per_page <= 100:
            raise APIError('invalid_pagination')
        params = {'page': page, 'perPage': per_page, 'returnType': 'JSON', 'serviceKey': self.key}
        if service_id:
            params['cond[서비스ID::EQ]'] = service_id
        if service_name:
            if endpoint != 'serviceList':
                raise APIError('name_filter_only_for_list')
            params['cond[서비스명::LIKE]'] = service_name
        if modified_since:
            if endpoint != 'serviceList':
                raise APIError('modified_filter_only_for_list')
            params['cond[수정일시::GTE]'] = modified_since
        req = Request(BASE + endpoint + '?' + urlencode(params), headers={'Accept': 'application/json', 'User-Agent': 'SupportPick-readonly-validation/1.0'})
        for attempt in range(2):
            self.requests += 1
            try:
                with self.opener.open(req, timeout=20) as response:
                    raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise APIError('response_too_large')
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise APIError('invalid_json') from None
                if not isinstance(data, dict) or not isinstance(data.get('data'), list):
                    raise APIError('invalid_response_schema')
                if any(not isinstance(row, dict) for row in data['data']):
                    raise APIError('invalid_row_schema')
                if data.get('currentCount') != len(data['data']):
                    raise APIError('response_count_mismatch')
                return redact(data, self.key)
            except HTTPError as exc:
                code = exc.code
                if code >= 500 and attempt == 0:
                    self.sleep(1)
                    continue
                raise APIError('http_' + str(code)) from None
            except (URLError, TimeoutError, OSError):
                if attempt == 0:
                    self.sleep(1)
                    continue
                raise APIError('network_error') from None
        raise APIError('retry_budget_exhausted')

def probe(client, output, service_name=None):
    """At most 3 normal requests / 6 with retries; no writing outside output."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    evidence = {'project': 'supportpick', 'mode': 'read_only_probe', 'status': 'failed',
                'checked_at': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
                'naver_accessed': False, 'published': False, 'endpoints': {},
                'facts_verified': False, 'application_open_verified': False}
    try:
        listing = client.get('serviceList', service_name=service_name)
        if not listing['data']:
            raise APIError('empty_service_list')
        service_id = listing['data'][0].get('서비스ID')
        if not isinstance(service_id, str) or not service_id.strip():
            raise APIError('missing_service_id')
        evidence['service_id'] = service_id
        for endpoint in ENDPOINTS:
            payload = listing if endpoint == 'serviceList' else client.get(endpoint, service_id)
            if not payload['data']:
                raise APIError('empty_' + endpoint)
            if any(row.get('서비스ID') != service_id for row in payload['data']):
                raise APIError('service_id_mismatch_' + endpoint)
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
            (output / (endpoint + '.json')).write_bytes(raw)
            evidence['endpoints'][endpoint] = {'status': 'passed', 'count': len(payload['data']),
                                              'sha256': hashlib.sha256(raw).hexdigest()}
        evidence['status'] = 'passed'
    except APIError as exc:
        evidence['error'] = str(exc)
    finally:
        evidence['request_count'] = client.requests
        (output / 'probe.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    return evidence

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--service-name')
    args = parser.parse_args()
    try:
        result = probe(Gov24(os.environ.get(SECRET_NAME, '')), args.output, args.service_name)
    except APIError as exc:
        result = {'status': 'failed', 'error': str(exc), 'request_count': 0}
        path = Path(args.output)
        path.mkdir(parents=True, exist_ok=True)
        (path / 'probe.json').write_text(json.dumps(result), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__':
    raise SystemExit(main())

