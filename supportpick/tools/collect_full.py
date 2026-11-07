"""Complete, resumable Gov24 snapshot. Never changes production data or prints URLs."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from gov24_transport import Gov24, APIError, SECRET_NAME

ENDPOINTS = ('serviceList', 'serviceDetail', 'supportConditions')
PER_PAGE = 100
SHARDS = 32
REGIONS = {'서울특별시':'서울','부산광역시':'부산','대구광역시':'대구','인천광역시':'인천','광주광역시':'광주','대전광역시':'대전','울산광역시':'울산','세종특별자치시':'세종','경기도':'경기','강원특별자치도':'강원','강원도':'강원','충청북도':'충북','충청남도':'충남','전북특별자치도':'전북','전라북도':'전북','전라남도':'전남','경상북도':'경북','경상남도':'경남','제주특별자치도':'제주'}

def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()

def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()

def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('wb') as f:
        f.write(encoded(value))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def fail(code):
    raise APIError(code)

def valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value))

def safe_url(value):
    if not isinstance(value, str):
        return ''
    try:
        u = urlsplit(value)
        if u.scheme != 'https' or u.username or u.password:
            return ''
        return value if any(u.hostname == s or (u.hostname or '').endswith('.'+s) for s in ('go.kr','gov.kr')) else ''
    except ValueError:
        return ''

def period(raw, kind=''):
    raw = raw or ''
    if not raw.strip():
        return {'periodKind':'not_provided','startDate':None,'endDate':None}
    if re.search(r'예산.{0,12}소진|소진.{0,8}시', raw):
        return {'periodKind':'budget_limited','startDate':None,'endDate':None}
    if re.search(r'상시|연중|수시', raw+' '+(kind or '')):
        return {'periodKind':'ongoing','startDate':None,'endDate':None}
    dates = []
    for y,m,d in re.findall(r'(20\d{2})\s*[.년/-]\s*(\d{1,2})\s*[.월/-]\s*(\d{1,2})', raw):
        try:
            dates.append(datetime(int(y),int(m),int(d)).date().isoformat())
        except ValueError:
            return {'periodKind':'needs_check','startDate':None,'endDate':None}
    if len(dates) == 2 and re.search(r'~|∼|～|부터', raw) and dates[0] <= dates[1]:
        return {'periodKind':'fixed','startDate':dates[0],'endDate':dates[1]}
    if len(dates) == 1 and re.search(r'까지|마감|종료', raw):
        return {'periodKind':'fixed','startDate':None,'endDate':dates[0]}
    return {'periodKind':'needs_check','startDate':None,'endDate':None}

def region(org, target):
    # Agency jurisdiction is evidence about the agency, not a residency ruling.
    for name, value in REGIONS.items():
        if org.startswith(name):
            return value, 'agency_jurisdiction', org
    if re.search(r'전국\s*(대상|거주|지역|민)', target):
        return '전국', 'target_text', target[:300]
    return '확인 필요', 'not_provided', ''

def normalize(listing, detail, conditions, checked_at, generation):
    sid = listing['서비스ID']
    def field(key, fallback=''):
        value = detail.get(key)
        if value is None or value == '':
            value = listing.get(key, fallback)
        return value if isinstance(value, str) else fallback
    title, org = field('서비스명'), field('소관기관명')
    if not title or not org:
        fail('missing_required_text')
    target = field('지원대상')
    rg, rg_kind, rg_raw = region(org, target)
    raw_period = field('신청기한')
    official = safe_url(listing.get('상세조회URL'))
    conflicts = [key for key in ('서비스명','소관기관명','지원대상','지원내용','신청기한','지원유형')
                 if listing.get(key) and detail.get(key) and listing[key] != detail[key]]
    audiences = [x.strip() for x in re.split(r'[,|+/]', listing.get('사용자구분') or '') if x.strip()]
    types = [x.strip() for x in re.split(r'[,|+/]', field('지원유형')) if x.strip()]
    common = {'id':sid,'title':title,'organization':org,'category':listing.get('서비스분야') or '분야 미제공',
        'region':rg,'regionBasis':rg_kind,'regionEvidence':rg_raw,'audience':audiences,
        'supportType':field('지원유형') or '방식 미제공','supportTypes':types,
        'summary':listing.get('서비스목적요약') or field('서비스목적') or '상세 안내를 확인하세요.',
        'targetPreview':target[:240]+('…' if len(target)>240 else ''),'period':raw_period or '기간 미제공',
        **period(raw_period,field('신청기한유형')),'officialUrl':official,
        'officialLinkStatus':'provided' if official else 'needs_check','source':'보조금24 OpenAPI',
        'sourceUpdatedAt':{'list':listing.get('수정일시'),'detail':detail.get('수정일시')},
        'checkedAt':checked_at,'factsVerifiedAt':None,'verification':'source_only','applicationOpenVerified':False,
        'sourceConflicts':conflicts,'generation':generation,
        'detailShard':hashlib.sha256(sid.encode()).hexdigest()[:2]}
    common['detailShard'] = f'{int(common["detailShard"],16) % SHARDS:02d}'
    full = {**common,'target':target,'support':field('지원내용'),'method':field('신청방법'),
        'documents':field('구비서류'),'contact':field('문의처',listing.get('전화문의') or ''),
        'selection':field('선정기준'),'applicationUrl':safe_url(detail.get('온라인신청사이트URL')),
        'rawSource':{'serviceList':listing,'serviceDetail':detail,'supportConditions':conditions}}
    return common, full

class GuardedOpener:
    def __init__(self, opener, max_requests=800, interval=.35):
        self.opener,self.max_requests,self.interval = opener,max_requests,interval
        self.calls,self.last = 0,0
    def open(self, *args, **kwargs):
        if self.calls >= self.max_requests:
            fail('request_budget_exhausted')
        time.sleep(max(0, self.interval-(time.monotonic()-self.last)))
        self.last = time.monotonic()
        self.calls += 1
        return self.opener.open(*args, **kwargs)

def validate_page(payload, endpoint, page, total=None):
    if not isinstance(payload,dict) or not isinstance(payload.get('data'),list):
        fail('response_schema')
    if any(type(payload.get(k)) is not int for k in ('page','perPage','totalCount','currentCount','matchCount')):
        fail('response_counts_schema')
    n=payload['totalCount']
    if not 0 < n <= 50000 or payload['matchCount']!=n:
        fail('unfiltered_total_invalid')
    if total is not None and n!=total:
        fail('total_changed_during_collection')
    if payload['page']!=page or payload['perPage']!=PER_PAGE:
        fail('page_identity_mismatch')
    expected=min(PER_PAGE,max(0,n-(page-1)*PER_PAGE))
    if payload['currentCount']!=len(payload['data']) or len(payload['data'])!=expected:
        fail('partial_or_empty_page')
    if any(not isinstance(row,dict) or not valid_id(row.get('서비스ID')) for row in payload['data']):
        fail('invalid_service_id')
    return n

def collect(client, directory, generation, max_services=20000):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',generation):
        fail('invalid_generation')
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    manifest_path=root/'checkpoint.json'
    checkpoint=json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'version':1,'generation':generation,'startedAt':now(),'pages':{}}
    if checkpoint.get('generation')!=generation or checkpoint.get('version')!=1:
        fail('checkpoint_identity')
    report={'project':'supportpick','generation':generation,'status':'collecting','startedAt':checkpoint['startedAt'],
        'coverage':'Currently connected Gov24 API, all unfiltered pages of three endpoints',
        'endpoints':{},'published':False,'scheduled':False,'factsVerified':False,'applicationOpenVerified':False}
    datasets={}; detail_times={}
    write(root/'report.json',report)
    try:
        for endpoint in ENDPOINTS:
            records={};received=0;page=1;total=None;duplicates=0
            while True:
                name=f'{endpoint}/{page:05d}.json';path=root/'pages'/name
                prior=checkpoint['pages'].get(name)
                if prior:
                    envelope=json.loads(path.read_text())
                    if digest(envelope['response'])!=prior['sha256']:
                        fail('checkpoint_hash_mismatch')
                else:
                    payload=client.get(endpoint,page=page,per_page=PER_PAGE)
                    validate_page(payload,endpoint,page,total)
                    envelope={'endpoint':endpoint,'page':page,'receivedAt':now(),'response':payload}
                    if path.exists():
                        old=json.loads(path.read_text())
                        if digest(old['response'])!=digest(payload):
                            fail('unconfirmed_checkpoint_conflict')
                    else:
                        write(path,envelope)
                    checkpoint['pages'][name]={'sha256':digest(payload),'receivedAt':envelope['receivedAt']}
                    write(manifest_path,checkpoint)
                if envelope.get('endpoint')!=endpoint or envelope.get('page')!=page:
                    fail('checkpoint_page_identity')
                payload=envelope['response']
                total=validate_page(payload,endpoint,page,total)
                if total>max_services:
                    fail('service_budget_exceeded')
                for row in payload['data']:
                    sid=row['서비스ID'];received+=1
                    if sid in records:
                        duplicates+=1
                        if digest(records[sid])!=digest(row):
                            fail('duplicate_id_conflict')
                    records[sid]=row
                    if endpoint=='serviceDetail':
                        detail_times[sid]=envelope['receivedAt']
                report['endpoints'][endpoint]={'reportedTotal':total,'receivedCount':received,
                    'uniqueCount':len(records),'duplicateCount':duplicates,'completedPages':page,
                    'expectedPages':math.ceil(total/PER_PAGE)}
                write(root/'report.json',report)
                if page>=math.ceil(total/PER_PAGE):
                    break
                page+=1
            if received!=total or len(records)!=total or duplicates:
                fail('page_coverage_mismatch')
            datasets[endpoint]=records
        ids=set(datasets['serviceList'])
        if any(set(datasets[x])!=ids for x in ENDPOINTS[1:]):
            report['joinDifferences']={x:len(ids.symmetric_difference(datasets[x])) for x in ENDPOINTS[1:]}
            fail('detail_or_conditions_join_mismatch')
        # Recheck source counts after traversal. Per-page duplicate and ID checks protect paging coverage;
        # this is not an API snapshot token and does not promise transaction-level source consistency.
        for endpoint in ENDPOINTS:
            end=client.get(endpoint,page=1,per_page=PER_PAGE)
            validate_page(end,endpoint,1,report['endpoints'][endpoint]['reportedTotal'])
            first=json.loads((root/'pages'/endpoint/'00001.json').read_text())['response']
            if digest(first)!=digest(end):
                fail('source_changed_at_snapshot_boundary')
        success_at=now();snapshot=root/'snapshot';snapshot.mkdir(exist_ok=True)
        light=[];shards={f'{i:02d}':{} for i in range(SHARDS)}
        for sid in sorted(ids):
            a,b=normalize(datasets['serviceList'][sid],datasets['serviceDetail'][sid],datasets['supportConditions'][sid],detail_times[sid],generation)
            a['dataCollectedAt']=success_at;b['dataCollectedAt']=success_at
            light.append(a);shards[a['detailShard']][sid]=b
        feed={'schemaVersion':1,'generation':generation,'updatedAt':success_at,'collectionSucceededAt':success_at,
            'factsVerifiedAt':None,'isSample':False,'sourceCount':len(ids),
            'coverage':f'보조금24 연결 API 제공 범위 {len(ids):,}건. 국내 모든 지원사업을 의미하지 않습니다.',
            'detailBase':f'details/{generation}/','items':light}
        write(snapshot/'data.json',feed)
        (snapshot/'data.js').write_text('window.SUPPORTPICK_DATA = '+encoded(feed).decode().replace('<','\\u003c')+';\n')
        for key,records in shards.items():
            if records:
                write(snapshot/'details'/generation/(key+'.json'),{'generation':generation,'items':records})
        report.update(status='passed',finishedAt=now(),collectionSucceededAt=success_at,storedCount=len(light),
            sampleCount=0,normalRequestEstimate=sum(v['expectedPages'] for v in report['endpoints'].values())+3,
            pageResponses=len(checkpoint['pages']),feedSha256=hashlib.sha256((snapshot/'data.json').read_bytes()).hexdigest(),
            sourceConsistency='No snapshot token: totals and boundary pages stable; unique IDs and all endpoint sets matched')
        write(snapshot/'collection-report.json',report)
        report['snapshotPath']=str(snapshot)
    except Exception as exc:
        code=str(exc) if isinstance(exc,APIError) and re.fullmatch(r'[a-z0-9_:]+',str(exc)) else 'internal_validation_error'
        report.update(status='failed',errorCode=code,finishedAt=now(),resumeDirectory=str(root))
    finally:
        report['requestsThisInvocation']=getattr(getattr(client,'opener',None),'calls',getattr(client,'requests',0))
        write(root/'report.json',report)
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--generation',required=True)
    parser.add_argument('--max-requests',type=int,default=800)
    args=parser.parse_args()
    try:
        client=Gov24(os.environ.get(SECRET_NAME,''))
        client.opener=GuardedOpener(client.opener,args.max_requests)
        result=collect(client,args.output,args.generation)
    except APIError as exc:
        result={'status':'failed','errorCode':str(exc),'published':False}
        write(Path(args.output)/'report.json',result)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':
    raise SystemExit(main())
