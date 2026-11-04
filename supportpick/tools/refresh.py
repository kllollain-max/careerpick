"""Validate immutable generations and promote only a complete candidate."""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil
from pathlib import Path
from collect_full import Gov24,GuardedOpener,SECRET_NAME,collect,write,now,ENDPOINTS,APIError

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def relative(name):
    p=Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('unsafe_snapshot_path')
    return p

def verify_snapshot(path,expected_manifest=None):
    root=Path(path)
    if root.is_symlink():raise ValueError('unsafe_snapshot_root')
    if expected_manifest and sha(root/'manifest.json')!=expected_manifest:raise ValueError('manifest_mismatch')
    manifest=json.loads((root/'manifest.json').read_text())
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=set(manifest['files']):raise ValueError('snapshot_file_set_mismatch')
    for name,digest in manifest['files'].items():
        p=root/relative(name)
        if p.is_symlink() or not p.is_file() or sha(p)!=digest:raise ValueError('snapshot_file_hash_mismatch')
    feed=json.loads((root/'data.json').read_text())
    embedded=(root/'data.js').read_text().strip().removeprefix('window.SUPPORTPICK_DATA = ').removesuffix(';')
    if json.loads(embedded)!=feed:raise ValueError('index_pair_mismatch')
    return feed

def read_current(state):
    state=Path(state);pointer=state/'current.json'
    if not pointer.exists():return None,None
    value=json.loads(pointer.read_text());path=state/relative(value['path'])
    if value.get('version')!=1 or not value['path'].startswith('snapshots/'):raise ValueError('pointer_schema')
    feed=verify_snapshot(path,value['manifestSha256'])
    if feed['generation']!=value['generation'] or len(feed['items'])!=value['count']:raise ValueError('pointer_identity')
    return value,path

def validate_candidate(directory):
    root=Path(directory);r=json.loads((root/'report.json').read_text());snapshot=root/'snapshot'
    if r.get('status')!='passed' or r.get('sampleCount')!=0:raise ValueError('candidate_not_complete')
    feed=json.loads((snapshot/'data.json').read_text())
    n=len(feed['items']);generation=feed.get('generation')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',generation or '') or n<=0 or feed.get('isSample') is not False:raise ValueError('candidate_identity')
    if sha(snapshot/'data.json')!=r['feedSha256'] or n!=r['storedCount']:raise ValueError('candidate_feed_mismatch')
    for e in ENDPOINTS:
        stats=r['endpoints'][e]
        if stats['reportedTotal']!=n or stats['uniqueCount']!=n or stats['receivedCount']!=n or stats['duplicateCount']!=0 or stats['completedPages']!=stats['expectedPages']:raise ValueError('candidate_coverage_mismatch')
    ids={p['id'] for p in feed['items']}
    if len(ids)!=n or any(p.get('isSample') for p in feed['items']):raise ValueError('candidate_duplicate_or_sample')
    full={}
    for path in (snapshot/'details'/generation).glob('*.json'):
        shard=json.loads(path.read_text())
        if shard.get('generation')!=generation or set(full)&set(shard['items']):raise ValueError('detail_identity')
        full.update(shard['items'])
    if set(full)!=ids:raise ValueError('detail_coverage')
    for item in feed['items']:
        d=full[item['id']]
        if d['id']!=item['id'] or d['generation']!=generation or d['title']!=item['title']:raise ValueError('detail_join')
        if {d['rawSource'][e]['서비스ID'] for e in ENDPOINTS}!={item['id']}:raise ValueError('raw_source_join')
    return r,feed,snapshot

def install_candidate(directory,state):
    state=Path(state);state.mkdir(parents=True,exist_ok=True)
    old,_=read_current(state)
    report,feed,source=validate_candidate(directory)
    if old and len(feed['items'])<old['count']*.9:raise ValueError('abnormal_count_drop')
    generation=feed['generation'];destination=state/'snapshots'/generation
    if destination.exists():
        current=verify_snapshot(destination)
        if current!=feed:raise ValueError('generation_collision')
    else:
        staged=state/'snapshots'/('.stage-'+generation)
        if staged.exists():raise ValueError('staged_generation_exists')
        staged.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source,staged)
        write(staged/'report.json',report)
        files={str(p.relative_to(staged)):sha(p) for p in staged.rglob('*') if p.is_file()}
        write(staged/'manifest.json',{'version':1,'generation':generation,'files':files})
        verify_snapshot(staged)
        os.replace(staged,destination)
    pointer={'version':1,'generation':generation,'path':'snapshots/'+generation,
        'manifestSha256':sha(destination/'manifest.json'),'count':len(feed['items']),
        'lastSuccessAt':report['collectionSucceededAt']}
    write(state/'current.json',pointer)
    write(state/'status.json',{'status':'success','generation':generation,'lastAttemptAt':report['finishedAt'],
        'lastSuccessAt':pointer['lastSuccessAt'],'count':pointer['count'],'published':False})
    return pointer

def mark_failure(state,code):
    state=Path(state);state.mkdir(parents=True,exist_ok=True)
    try:current,_=read_current(state)
    except Exception:current=None
    write(state/'status.json',{'status':'failed','lastAttemptAt':now(),'errorCode':code,
        'generation':current['generation'] if current else None,
        'lastSuccessAt':current['lastSuccessAt'] if current else None,'count':current['count'] if current else 0,
        'published':False})

def main():
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--generation');p.add_argument('--output');p.add_argument('--candidate');args=p.parse_args()
    try:
        candidate=args.candidate
        if not candidate:
            if not args.generation or not args.output:raise ValueError('missing_run_arguments')
            client=Gov24(os.environ.get(SECRET_NAME,''));client.opener=GuardedOpener(client.opener,800)
            result=collect(client,args.output,args.generation)
            if result['status']!='passed':raise ValueError(result.get('errorCode','collection_failed'))
            candidate=args.output
        result=install_candidate(candidate,args.state)
        print(json.dumps({'status':'passed',**result},ensure_ascii=False));return 0
    except Exception as exc:
        code=str(exc) if re.fullmatch(r'[a-z0-9_:]+',str(exc)) else 'refresh_validation_failed'
        mark_failure(args.state,code)
        print(json.dumps({'status':'failed','errorCode':code,'previousDataPreserved':True}));return 1

if __name__=='__main__':raise SystemExit(main())
