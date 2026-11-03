"""Probe runner write access outside live slot claims; never call Meta."""
import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def main():
    history = json.loads(Path('threads_posted.json').read_text())
    records = history['records']
    if len(records) < 40 or any(r.get('status') == 'pending' or r.get('request_status') in ('attempted', 'uncertain') for r in records):
        raise SystemExit('History incomplete or unresolved; keep publishing disabled')
    if not any(r.get('threads_post_id') == '18029250455877919' and r.get('reply_post_id') == '17909910720593443' and r.get('engagement_post_id') == '18132626512765431' for r in records):
        raise SystemExit('Verified migrated record missing')
    if os.environ.get('PUBLISH_ENABLED') == 'true' or os.environ.get('MIGRATION_READY') == 'true':
        raise SystemExit('Preflight requires both publishing gates OFF')
    repo, token = os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN']
    branch = 'threads-publisher-state'
    def request(method, path, payload=None):
        req = urllib.request.Request('https://api.github.com/repos/' + repo + path,
            data=None if payload is None else json.dumps(payload).encode(), method=method,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise SystemExit('State preflight failed: HTTP ' + str(exc.code)) from None
    tree = request('GET', '/git/trees/' + branch + '?recursive=1')
    if tree.get('truncated'):
        raise SystemExit('State inventory incomplete')
    claims = [x['path'] for x in tree['tree'] if x['path'].startswith('threads-claims/') and x['path'].endswith('.json')]
    for path in claims:
        content = request('GET','/contents/'+path+'?ref='+branch)
        claim = json.loads(base64.b64decode(content['content']))
        if claim.get('state') not in ('accepted','historical_verified'):
            raise SystemExit('Remote unresolved claim; do not enable publishing')
    payload = {'run_id':os.environ['GITHUB_RUN_ID'],'kind':'migration_write_probe','publishes':0}
    path = '/contents/threads-state-probes/' + os.environ['GITHUB_RUN_ID'] + '.json'
    result = request('PUT',path,{'message':'Verify Threads runner state access without publishing','branch':branch,'content':base64.b64encode(json.dumps(payload).encode()).decode()})
    if not result.get('content',{}).get('sha'):
        raise SystemExit('State write unconfirmed')
    readback = request('GET',path+'?ref='+branch)
    if json.loads(base64.b64decode(readback['content'])) != payload:
        raise SystemExit('State readback mismatch')
    print('Runner state create/readback verified; unresolved claims: 0; actual publications: 0')


if __name__ == '__main__': main()
