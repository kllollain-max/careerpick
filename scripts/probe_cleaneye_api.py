"""Bounded, read-only schema discovery. Never print credential-bearing URLs."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

OUT = Path('cleaneye-api-probe-output')
MAX_BYTES = 16 * 1024 * 1024
KEY = urllib.parse.unquote(os.environ.get('CLEANEYE_KEY', '').strip())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('redirect_rejected')


class RegionForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.select = None
        self.option = None
        self.fields = []
        self.scripts = []
        self.options = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.scripts.append(attrs['src'])
        if tag == 'select':
            self.select = attrs.get('name') or attrs.get('id')
        if tag == 'option':
            self.option = {'select':self.select, 'value':attrs.get('value'), 'label':''}
        if tag == 'input' and re.search(r'sido|region|work|local', attrs.get('name','') + attrs.get('id',''), re.I):
            self.fields.append({k:attrs[k] for k in ('name','id','type','value') if k in attrs})

    def handle_data(self, data):
        if self.option is not None:
            self.option['label'] += data.strip()

    def handle_endtag(self, tag):
        if tag == 'option' and self.option is not None:
            self.options.append(self.option)
            self.option = None
        if tag == 'select':
            self.select = None


def inspect_region_form():
    url = 'https://job.cleaneye.go.kr/user/ypRecruitment.do'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=30) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            return {'error':'page_too_large'}
        text = raw.decode('utf-8', errors='replace')
        parser = RegionForm()
        parser.feed(text)
        relevant = []
        for script in re.findall(r'<script\b[^>]*>([\s\S]*?)</script>', text, re.I):
            for line in script.splitlines():
                if re.search(r'sido|region|ajax|codeList|commonCode', line, re.I) and not re.search(r'token|password|secret|csrf', line, re.I):
                    relevant.append(line.strip()[:500])
        return {'url':url, 'options':parser.options[:300], 'fields':parser.fields[:100], 'scripts':parser.scripts[:100], 'code_lines':relevant[:100]}
    except Exception:
        return {'url':url, 'error':'public_form_unavailable'}


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
    form = {'status':'not_retried_after_public_form_timeout'}
    region_info, regions = {'status':'not_retried_after_service_not_registered'}, []
    codes = []
    if region_info.get('total_count') == str(len(regions)) and regions:
        for row in regions:
            code = row.get('SIDO_CD', '')
            if re.fullmatch(r'[0-9]{1,12}', code) and code not in codes:
                codes.append(code)
    region_info['regions'] = regions
    # Bounded exploratory values: only successful responses can establish this
    # service's code format. These candidates do not establish national scope.
    attempts = []
    rows = []
    for selected in ('6110000', '1100000000', '110000', '1000', '01', '1'):
        employment_info, rows = query('openApiEmployInfo/openXmlEmployInfo', {'sidoCd':selected, 'type':'xml'})
        attempts.append({'region':selected, **employment_info})
        if rows or employment_info.get('http_status') not in (None, 200):
            break
    employment_info['queried_region'] = selected
    employment_info['unconfirmed_region_probe'] = not bool(codes)
    employment_info['statuses'] = sorted({row.get('STATUS', '') for row in rows})
    employment_info['employment_types'] = sorted({row.get('JOB_TYPE', '') for row in rows})
    employment_info['sample'] = [{key:row.get(key) for key in ('NO','ENT_NAME','ENT_TITLE','SIDO_CD','STATUS','JOB_TYPE','PUB_DATE','PUB_END_DATE','UPD_DATE','URL')} for row in rows[:3]]
    report = {'public_region_form':form, 'region_service':region_info, 'employment_service':employment_info, 'codes':codes, 'exploratory_attempts':attempts, 'api_requests':len(attempts)}
    (OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (OUT/'public-employment-rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if rows else 1


if __name__ == '__main__':
    raise SystemExit(main())
