"""Stage a conservative, explicitly scoped GOJOBS feed; preserve all prior IDs."""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gojobs
from scripts.verify_gojobs_recent_window import collect_window, KST


def merge(previous, report, now):
    if report.get('complete_window') is not True:
        raise ValueError('incomplete_window')
    received=sum(item['records'] for item in report['total_by_filter'].values())
    baseline=previous.get('last_received',0)
    if baseline and received<baseline*.7:
        raise ValueError('unexpected_window_decrease')
    old={p['id']:p for p in previous.get('posts',[])}
    if len(old)!=len(previous.get('posts',[])):
        raise ValueError('duplicate_previous_id')
    rows=dict(old)
    for item in report['official_page_samples']:
        if item.get('classification',{}).get('recruiting') is not True:
            continue
        if not item['id'].startswith('gojobs-') or not item.get('content'):
            raise ValueError('invalid_verified_record')
        identity=item['id']
        source=next(p for p in report['records'] if 'gojobs-'+p['id']==identity)
        rows[identity]={'id':identity,'type':'j','gojobs':True,'source':'나라일터',
            'cat':'나라일터 지방공무원 모집','title':item['title'],'org':item['org'],
            'desc':'공식 모집공고 · 접수 시각과 첨부는 원문 확인',
            'url':item['url'],'src':item['url'],
            'pub':source['registered_date']+'T00:00:00+09:00',
            'start':item['application_start'],
            'due':item['application_end']+'T23:59:59+09:00','dueHasTime':False,
            'emp':['임기제'] if '임기제' in item['title'] else [],'edu':[],
            'region':item['region'],'text':item['content'],
            'gojobsDetail':{'공식 모집 내용':item['content']}}
    posts=sorted(rows.values(),key=lambda p:p['id'])
    changed=posts!=sorted(old.values(),key=lambda p:p['id'])
    metrics={'before':len(old),'new':len(rows.keys()-old.keys()),
        'modified':sum(rows[k]!=old[k] for k in old.keys()&rows.keys()),'deleted':0,
        'after':len(rows),'received_in_window':received,'verified_this_run':len(report['official_page_samples']),
        'open':sum(p['start']<=now.date().isoformat()<=p['due'][:10] for p in posts),
        'archived':sum(p['due'][:10]<now.date().isoformat() for p in posts)}
    feed={'updated':now.isoformat(timespec='seconds'),'last_received':received,
        'scope':'지방공무원 g02/e01,e02 · 최근 14일 등록 목록 전체 조회 · 마감 임박 후보 최대8건 원문 검증; 전국 전체 채용 아님',
        'posts':posts}
    return (feed if changed else previous),changed,metrics


def main():
    now=datetime.now(KST)
    output=Path('gojobs-operation-output');output.mkdir(exist_ok=True)
    source=Path('gojobs.json');before=source.read_bytes() if source.exists() else None
    report={'source':'gojobs','started_at':now.isoformat(timespec='seconds'),'status':'failed_preserved'}
    try:
        previous=json.loads(before) if before else {'posts':[]}
        client=gojobs.Client(os.environ.get('GOJOBS_KEY',''))
        result=collect_window(client,(now.date()-timedelta(days=14)).isoformat(),now.date().isoformat())
        feed,changed,counts=merge(previous,result,now)
        if not feed.get('posts'):
            raise ValueError('no_verified_initial_records')
        client._reject_credential_echo(feed)
        (output/'gojobs.json').write_text(json.dumps(feed,ensure_ascii=False,indent=2)+'\n')
        report.update(status='changed' if changed else 'unchanged',changed=changed,counts=counts,
            authentication_verified=True,complete_window=True,window=result['window'],
            requests=result['requests'],snapshot_at=feed['updated'],
            official_page_verified=sum('verification_error' not in p for p in result['official_page_samples']),
            official_page_failed=sum('verification_error' in p for p in result['official_page_samples']))
    except gojobs.APIError as error:
        report['error']=error.safe_code
    except Exception:
        report['error']='candidate_validation_failed'
    report['verified_at']=datetime.now(KST).isoformat(timespec='seconds')
    report['original_preserved']=(source.read_bytes() if source.exists() else None)==before
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['status'] in ('changed','unchanged') else 1


if __name__=='__main__':
    raise SystemExit(main())
