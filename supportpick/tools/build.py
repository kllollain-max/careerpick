"""Build an allowlisted site from an integrity-checked immutable generation."""
import argparse,hashlib,json,os,re,shutil
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote,quote
from html import escape
from refresh import read_current,verify_snapshot
from bootstrap_state import ensure_bootstrap
ROOT=Path(__file__).resolve().parents[1]
STATIC=('index.html','privacy.html','about.html','icon.svg','careerpick-base.css','styles.css','core.js','app.js')
class Links(HTMLParser):
    def __init__(self,output):super().__init__();self.output=output
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key not in ('href','src') or not value or urlsplit(value).scheme or value.startswith('#'):continue
            path=urlsplit(value).path
            target=(self.output/path).resolve() if path!='./' else self.output/'index.html'
            if not target.is_file() or not target.is_relative_to(self.output):raise ValueError('missing_or_unsafe_local_asset')
def build(destination,state=None,allow_sample=False,public_base=None):
    output=Path(destination).resolve()
    if output==ROOT or ROOT.is_relative_to(output) or (output.is_relative_to(ROOT) and output!=ROOT/'dist'):raise ValueError('unsafe_output_directory')
    if output.exists() and any(output.iterdir()):raise ValueError('output_not_empty')
    state=Path(state or ROOT/'collection-state')
    if state.resolve()==(ROOT/'collection-state').resolve():ensure_bootstrap(state)
    pointer,snapshot=read_current(state)
    if public_base:
        parsed=urlsplit(public_base)
        if parsed.scheme!='https' or parsed.hostname!='kllollain-max.github.io' or parsed.path!='/supportpick/' or parsed.query or parsed.fragment:raise ValueError('unapproved_public_base')
    if not pointer and not allow_sample:raise ValueError('complete_snapshot_required')
    source=snapshot or ROOT
    feed=verify_snapshot(snapshot) if snapshot else json.loads((ROOT/'data.json').read_text())
    if pointer and (feed.get('isSample') is not False or len(feed['items'])!=pointer['count']):raise ValueError('sample_not_operational')
    output.mkdir(parents=True,exist_ok=True)
    for name in STATIC:
        p=ROOT/name
        if p.is_symlink() or not p.is_file():raise ValueError('unsafe_static_source')
        shutil.copyfile(p,output/name)
        if public_base and name.endswith('.html'):
            text=(output/name).read_text().replace('content="noindex,nofollow"','content="index,follow"')
            text=text.replace('<span class="preview-tag">미리보기</span>','').replace(' · 공개 전 미리보기','')
            canonical=public_base+('' if name=='index.html' else name)
            text=text.replace('</head>','<link rel="canonical" href="'+escape(canonical,quote=True)+'"></head>')
            (output/name).write_text(text)
    fields={'id','title','organization','category','region','regionBasis','audience','supportType','supportTypes','summary','targetPreview','period','periodKind','startDate','endDate','officialUrl','officialLinkStatus','source','sourceUpdatedAt','checkedAt','detailShard'}
    public_feed={**feed,'items':[{k:v for k,v in row.items() if k in fields} for row in feed['items']]}
    public_json=json.dumps(public_feed,ensure_ascii=False,separators=(',',':'))
    (output/'data.json').write_text(public_json)
    (output/'data.js').write_text('window.SUPPORTPICK_DATA = '+public_json.replace('<','\\u003c')+';\n')
    generations=[]
    if snapshot:
        candidates=[snapshot]+sorted((state/'snapshots').iterdir(),key=lambda x:x.name,reverse=True)
        for candidate in candidates:
            if candidate in generations or candidate.name.startswith('.') or not candidate.is_dir():continue
            verify_snapshot(candidate);generations.append(candidate)
            details=candidate/'details'
            if details.exists():
                for shard_path in details.rglob('*.json'):
                    shard=json.loads(shard_path.read_text());public_rows={}
                    for sid,row in shard['items'].items():
                        public={k:v for k,v in row.items() if k!='rawSource'}
                        raw=row.get('rawSource',{})
                        public['sourceDifferences']={key:{'list':raw.get('serviceList',{}).get(key),'detail':raw.get('serviceDetail',{}).get(key)} for key in row.get('sourceConflicts',[])}
                        public_rows[sid]=public
                    target=output/'details'/shard_path.relative_to(details);target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_text(json.dumps({'generation':shard['generation'],'items':public_rows},ensure_ascii=False,separators=(',',':')))
            if len(generations)==2:break
    status=json.loads((state/'status.json').read_text()) if (state/'status.json').exists() else {'status':'preview','generation':feed.get('generation'),'lastSuccessAt':feed.get('updatedAt'),'count':len(feed['items'])}
    (output/'status.json').write_text(json.dumps(status,ensure_ascii=False));(output/'.nojekyll').write_text('')
    secret=os.environ.get('SUPPORTPICK_GOV24_SERVICE_KEY','')
    secret_variants={secret,unquote(secret),quote(unquote(secret),safe=''),quote(quote(unquote(secret),safe=''),safe='')}-{''}
    forbidden=re.compile(r'gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:servicekey|access_token|authorization)=',re.I)
    files={}
    for p in sorted(output.rglob('*')):
        if not p.is_file():continue
        if p.is_symlink() or p.stat().st_nlink!=1:raise ValueError('linked_public_file')
        raw=p.read_bytes();text=raw.decode('utf-8')
        if forbidden.search(text) or any(s in text for s in secret_variants):raise ValueError('public_secret_pattern_detected')
        if p.suffix=='.html':
            Links(output).feed(text)
            expected='index,follow' if public_base else 'noindex,nofollow'
            if '<meta name="robots" content="'+expected+'">' not in text:raise ValueError('indexing_policy_mismatch')
        files[str(p.relative_to(output))]=hashlib.sha256(raw).hexdigest()
    size=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
    if size>300*1024*1024:raise ValueError('public_size_budget')
    report={'publicFiles':len(files)+1,'bytes':size,'benefits':len(feed['items']),'generation':feed.get('generation'),'isSample':not bool(pointer),'published':False,'status':status['status'],'files':files}
    (output/'site-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return {k:v for k,v in report.items() if k!='files'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--state');p.add_argument('--allow-sample',action='store_true');p.add_argument('--public-base');args=p.parse_args()
    print(json.dumps(build(args.output,args.state,args.allow_sample,args.public_base),ensure_ascii=False,indent=2))
