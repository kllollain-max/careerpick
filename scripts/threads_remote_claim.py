"""Explicit GitHub Contents claim for a single scheduled slot.

NOT wired to the live workflow. A successful create is the only permission to
send; ambiguous network responses never permit a send. One file per slot and
GitHub's create-only PUT provide compare-and-create between separate runners.
This does not reconcile existing legacy history or other publishing clients.
"""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


class ClaimError(RuntimeError):
    pass


class GitHubClaims:
    def __init__(self, repo, branch, token, opener=None):
        import re
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not branch or not token:
            raise ValueError('repository, branch and credential required')
        self.repo, self.branch, self.token = repo, branch, token
        self.opener = opener or urllib.request.urlopen

    def _path(self, slot):
        dt = datetime.fromisoformat(slot)
        if dt.tzinfo is None or dt.second or dt.microsecond:
            raise ValueError('aware minute-aligned slot required')
        return 'threads-claims/' + dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%MZ') + '.json'

    def _request(self, method, slot, payload=None):
        path = self._path(slot)
        url = 'https://api.github.com/repos/' + self.repo + '/contents/' + path
        if method == 'GET':
            url += '?' + urllib.parse.urlencode({'ref': self.branch})
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with self.opener(req, timeout=20) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            # Never expose request URLs, tokens or response bodies.
            raise ClaimError('remote claim unavailable or ambiguous') from None

    def begin(self, slot, run_id):
        if not str(run_id).isdigit():
            raise ValueError('run id required')
        data = {'slot':slot, 'run_id':str(run_id), 'state':'sending', 'post_id':None}
        payload = {'message':'Claim Threads slot before send', 'branch':self.branch,
                   'content':base64.b64encode(json.dumps(data).encode()).decode()}
        result = self._request('PUT',slot,payload)
        sha = result.get('content',{}).get('sha')
        if not isinstance(sha,str) or not sha:
            raise ClaimError('claim not confirmed; do not send')
        return sha

    def accept(self, slot, run_id, expected_sha, post_id):
        if not isinstance(post_id,str) or not post_id.isdigit() or not expected_sha:
            raise ValueError('post id and claim sha required')
        data={'slot':slot,'run_id':str(run_id),'state':'accepted','post_id':post_id}
        payload={'message':'Record Threads post receipt','branch':self.branch,'sha':expected_sha,
                 'content':base64.b64encode(json.dumps(data).encode()).decode()}
        try:
            result=self._request('PUT',slot,payload)
            if result.get('content',{}).get('sha'):
                return
        except ClaimError:
            pass
        # An accepted PUT response may be lost after GitHub commits it. Read
        # back the exact receipt instead of sending the Threads post again.
        try:
            observed = self.read(slot)
        except ClaimError:
            raise ClaimError('receipt persistence unconfirmed; reconcile manually') from None
        if observed == data:
            return
        raise ClaimError('receipt persistence unconfirmed; reconcile manually')

    def read(self, slot):
        result = self._request('GET',slot)
        try:
            return json.loads(base64.b64decode(result['content'], validate=False))
        except (KeyError, ValueError, TypeError):
            raise ClaimError('invalid remote state') from None
