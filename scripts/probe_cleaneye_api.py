"""Bounded, read-only schema discovery. Never print credential-bearing URLs."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path('cleaneye-api-probe-output')
MAX_BYTES = 16 * 1024 * 1024
KEY = urllib.parse.unquote(os.environ.get('CLEANEYE_KEY', '').strip())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('redirect_rejected')


def query(path, params):
    if not KEY:
        return {'error':'missing_key'}, []
    url = 'https://apis.data.go.kr/B551982/' + path
    request = urllib.request.Request(url + '?' + urllib.parse.urlencode({'serviceKey':KEY, **params}), headers={'Accept':'application/xml', 'User-Agent':'CareerPick'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=45) as response:
            raw = response.read(MAX_BYTES + 1)
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read(MAX_BYTES + 1)
        status = error.code
        error.close()
    except Exception:
        return {'error':'transport_failed'}, []
    if len(raw) > MAX_BYTES:
        return {'error':'response_too_large', 'http_status':status}, []
    text = raw.decode('utf-8-sig', errors='replace')
    candidate = text
    for _ in range(4):
        if KEY.casefold() in candidate.casefold():
            return {'error':'credential_echo_rejected'}, []
        candidate = urllib.parse.unquote(candidate)
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', text, re.I):
        return {'error':'unsafe_xml'}, []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        tokens = [v for v in ['SERVICE_KEY_IS_NOT_REGISTERED_ERROR','SERVICE_ACCESS_DENIED_ERROR','LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR','INVALID_REQUEST_PARAMETER_ERROR'] if v in text]
        return {'error':'non_xml_response', 'http_status':status, 'gateway_tokens':tokens}, []
    for node in root.iter():
        node.tag = node.tag.rsplit('}', 1)[-1]
    code = root.findtext('.//resultCode') or root.findtext('.//returnReasonCode') or ''
    code = code.strip()
    info = {'http_status':status, 'root_tag':root.tag, 'root_fields':[n.tag for n in root], 'result_code':code if re.fullmatch(r'[A-Za-z0-9_]{1,80}', code) else 'unrecognized', 'total_count':root.findtext('.//totalCount'), 'body_fields':[n.tag for n in root.find('body')] if root.find('body') is not None else []}
    if code not in {'0','00','200'}:
        info['error'] = 'api_not_successful'
        return info, []
    rows = [{child.tag:(child.text or '').strip() for child in item} for item in root.findall('.//item')]
    info.update(record_count=len(rows), record_fields=sorted({key for row in rows for key in row}))
    return info, rows


def main():
    OUT.mkdir(exist_ok=True)
    region_info, regions = query('openApiSidoCd3/openXmlSidoCd2', {'pageNo':'1','numOfRows':'300','type':'xml','ac_year':'2026'})
    codes = []
    if region_info.get('total_count') == str(len(regions)) and regions:
        for row in regions:
            code = row.get('SIDO_CD', '')
            if re.fullmatch(r'[0-9]{1,12}', code) and code not in codes:
                codes.append(code)
    region_info['regions'] = regions
    selected = codes[0] if codes else ''
    employment_info, rows = query('openApiEmployInfo/openXmlEmployInfo', {'sidoCd':selected, 'type':'xml'})
    employment_info['queried_region'] = selected
    employment_info['empty_region_probe'] = not bool(codes)
    employment_info['statuses'] = sorted({row.get('STATUS', '') for row in rows})
    employment_info['employment_types'] = sorted({row.get('JOB_TYPE', '') for row in rows})
    employment_info['sample'] = [{key:row.get(key) for key in ('NO','ENT_NAME','ENT_TITLE','SIDO_CD','STATUS','JOB_TYPE','PUB_DATE','PUB_END_DATE','UPD_DATE','URL')} for row in rows[:3]]
    report = {'region_service':region_info, 'employment_service':employment_info, 'codes':codes, 'requests':2}
    (OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (OUT/'public-employment-rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if rows else 1


if __name__ == '__main__':
    raise SystemExit(main())
