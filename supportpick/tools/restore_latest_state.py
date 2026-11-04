"""Restore a trusted main-branch operations artifact, validate before install."""
import io,json,os,re,shutil,tempfile,zipfile
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.parse import urlsplit
from refresh import read_current
from bootstrap_state import ensure_bootstrap
class StripCrossOriginAuth(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urlsplit(newurl).scheme!='https':raise ValueError('unsafe_redirect')
        new=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urlsplit(req.full_url).netloc!=urlsplit(newurl).netloc:new.remove_header('Authorization')
        return new
def main():
    ensure_bootstrap('collection-state')
    repo=os.environ.get('GITHUB_REPOSITORY','');token=os.environ.get('GITHUB_TOKEN','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or not token:raise ValueError('missing_runtime_context')
    opener=build_opener(StripCrossOriginAuth())
    def get(path,binary=False):
        req=Request('https://api.github.com/repos/'+repo+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
        with opener.open(req,timeout=60) as r:data=r.read(180*1024*1024+1)
        if len(data)>180*1024*1024:raise ValueError('artifact_size_limit')
        return data if binary else json.loads(data)
    try:runs=get('/actions/workflows/supportpick-operations.yml/runs?branch=main&status=completed&per_page=10')['workflow_runs']
    except Exception:
        print('Previous operations state unavailable; using the validated source baseline.');return
    for run in runs:
        if run.get('head_branch')!='main' or run.get('event') not in ('schedule','workflow_dispatch') or run.get('run_number',0)>=int(os.environ.get('GITHUB_RUN_NUMBER','2147483647')):continue
        artifacts=get('/actions/runs/'+str(run['id'])+'/artifacts')['artifacts']
        selected=next((a for a in artifacts if a['name']=='supportpick-runtime-state' and not a['expired']),None)
        if not selected:continue
        raw=get('/actions/artifacts/'+str(selected['id'])+'/zip',binary=True)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sum(i.file_size for i in z.infolist())>300*1024*1024:raise ValueError('expanded_size_limit')
                for info in z.infolist():
                    p=Path(info.filename)
                    if p.is_absolute() or '..' in p.parts or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('unsafe_artifact_member')
                z.extractall(root)
            pointer,_=read_current(root)
            if not pointer:raise ValueError('artifact_has_no_complete_snapshot')
            destination=Path('collection-state')
            if destination.exists():shutil.rmtree(destination)
            shutil.copytree(root,destination)
            print('Restored validated operations state for generation '+pointer['generation']);return
    print('No reusable operations artifact; using the validated source baseline.')
if __name__=='__main__':main()
