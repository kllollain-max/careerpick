"""Read existing collection receipts for Threads; never rewrite a source snapshot.

Only the scheduled main operations workflow's digest-verified artifact may prove
that unchanged exact bytes were checked again. No queue/review field supplies it.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit
import zipfile
from datetime import datetime, timedelta

REPO = 'kllollain-max/careerpick'
PROOF = '.threads-source-verification.json'


def moment(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.utcoffset() is None:
        raise ValueError('SOURCE_PROOF_NAIVE_TIME')
    return at


def digest(doc):
    value = {k: v for k, v in doc.items() if k not in ('_threads_verification', '_cleaneye')}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def verified_time(doc, now, scheduled, max_age_hours=24):
    """Keep the same 24h bound, against actual successful verification evidence."""
    if not 0 < max_age_hours <= 24:
        raise ValueError('SOURCE_PROOF_AGE_LIMIT')
    proof = doc.get('_threads_verification', {})
    if proof.get('document_sha256') != digest(doc):
        raise ValueError('SOURCE_PROOF_CONTENT_CHANGED')
    at = moment(proof['verified_at'])
    if at > now or max(now, scheduled) - at > timedelta(hours=max_age_hours):
        raise ValueError('SOURCE_PROOF_STALE')
    return at


def inspect_bundle(bundle, root, now):
    """Verify API provenance, ZIP digest, run/receipt times and exact source bytes."""
    run, artifact = bundle['run'], bundle['artifact']
    if (run.get('repository', {}).get('full_name') != REPO
            or run.get('path') != '.github/workflows/operations.yml'
            or run.get('event') != 'schedule' or run.get('head_branch') != 'main'
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'):
        raise ValueError('SOURCE_PROOF_RUN')
    linked = artifact.get('workflow_run', {})
    if (artifact.get('expired') is not False or artifact.get('name') != 'operation-' + str(run['id'])
            or linked.get('id') != run['id'] or linked.get('head_sha') != run['head_sha']
            or linked.get('head_branch') != 'main'
            or linked.get('repository_id') != run['repository']['id']
            or linked.get('head_repository_id') != run['repository']['id']):
        raise ValueError('SOURCE_PROOF_ARTIFACT')
    import base64
    data = base64.b64decode(bundle['zip_base64'], validate=True)
    if len(data) > 2_000_000 or artifact.get('digest') != 'sha256:' + hashlib.sha256(data).hexdigest():
        raise ValueError('SOURCE_PROOF_DIGEST')
    start, finish = moment(run['run_started_at']), moment(run['updated_at'])
    created = moment(artifact['created_at'])
    if not start <= created <= finish <= now or now - start > timedelta(hours=24):
        raise ValueError('SOURCE_PROOF_TIME')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in z.infolist()) > 2_000_000:
            raise ValueError('SOURCE_PROOF_ZIP')
        def read(name):
            return json.loads(z.read(name))
        if z.read('operations-output/previous-head.txt').decode().strip() != run['head_sha']:
            raise ValueError('SOURCE_PROOF_HEAD')
        report = read('operations-output/report.json')
        if (report.get('trigger') != 'schedule' or report.get('job_status') != 'success'
                or report.get('run_url') != 'https://github.com/' + REPO + '/actions/runs/' + str(run['id'])):
            raise ValueError('SOURCE_PROOF_RECEIPT')
        result = {}
        def same(name, expected):
            return isinstance(expected, str) and hashlib.sha256((Path(root) / name).read_bytes()).hexdigest() == expected
        if (report.get('source') == 'alio' and report.get('collection') == 'success'
                and report.get('validation') == 'success' and report.get('status') == 'unchanged'
                and report.get('changed') is False and report.get('originals_preserved') is True
                and all(same(n, report.get('source_hashes', {}).get(n)) for n in ('alio.json', 'alio-detail.json'))):
            at = moment(report['verified_at'])
            if start <= at <= created:
                result['alio'] = at.isoformat()
        clean = read('cleaneye-operation-output/report.json')
        if (clean.get('source') == 'cleaneye' and clean.get('status') == 'unchanged'
                and clean.get('changed') is False and clean.get('originals_preserved') is True
                and clean.get('authentication_verified') is True and clean.get('complete_collection') is True
                and clean.get('region_code_lookup_verified') is True
                and clean.get('successful_responses', {}).get('list') == 17
                and same('cleaneye.json', clean.get('candidate_sha256'))
                and same('cleaneye.json', clean.get('source_sha256', {}).get('cleaneye.json'))):
            # The existing Cleaneye receipt has no finish clock. Its real start
            # is a conservative lower bound, never the artifact/upload time.
            at = moment(clean['started_at'])
            if start <= at <= created:
                result['cleaneye'] = at.isoformat()
        return result


def attach(root, source, now):
    path = Path(root) / PROOF
    source.pop('_threads_verification', None)
    source.get('_cleaneye', {}).pop('_threads_verification', None)
    if not path.exists():
        return source
    try:
        bundle = json.loads(path.read_text())
        stamps = inspect_bundle(bundle, root, now)
        for name, doc in [('alio', source), ('cleaneye', source.get('_cleaneye', {}))]:
            if name in stamps:
                doc['_threads_verification'] = {'verified_at': stamps[name],
                    'document_sha256': digest(doc), 'run_id': bundle['run']['id'],
                    'artifact_id': bundle['artifact']['id'], 'artifact_digest': bundle['artifact']['digest']}
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile):
        # Missing/unusable proof never makes stale original timestamps fresh.
        pass
    return source


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        dest = urlsplit(newurl)
        if (dest.scheme != 'https' or dest.username or dest.password
                or not dest.hostname or not (dest.hostname == 'api.github.com'
                or dest.hostname.endswith('.blob.core.windows.net')
                or dest.hostname.endswith('.githubusercontent.com'))):
            raise ValueError('SOURCE_PROOF_REDIRECT')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if dest.hostname != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected


def fetch_bundle(token):
    """Read only the fixed repository's existing Actions run/artifact endpoints."""
    base = 'https://api.github.com/repos/' + REPO
    opener = urllib.request.build_opener(SafeRedirect())
    def get(url, binary=False):
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
            'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        with opener.open(req, timeout=20) as f:
            data = f.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('SOURCE_PROOF_RESPONSE_SIZE')
        return data if binary else json.loads(data)
    runs = get(base + '/actions/workflows/operations.yml/runs?branch=main&event=schedule&status=success&per_page=5')['workflow_runs']
    if not runs:
        raise ValueError('SOURCE_PROOF_NO_RUN')
    run = runs[0]
    artifacts = get(base + '/actions/runs/' + str(run['id']) + '/artifacts')['artifacts']
    matches = [a for a in artifacts if a.get('name') == 'operation-' + str(run['id']) and not a.get('expired')]
    if len(matches) != 1:
        raise ValueError('SOURCE_PROOF_ARTIFACT_NOT_UNIQUE')
    artifact = matches[0]
    import base64
    return {'run': run, 'artifact': artifact, 'zip_base64': base64.b64encode(
        get(base + '/actions/artifacts/' + str(artifact['id']) + '/zip', True)).decode()}


def main():
    from datetime import timezone
    root = Path(__file__).resolve().parents[1]
    path = root / PROOF
    # Do not reuse a previous run's proof when a fresh lookup fails.
    path.unlink(missing_ok=True)
    try:
        bundle = fetch_bundle(os.environ['THREADS_CLAIM_TOKEN'])
        stamps = inspect_bundle(bundle, root, datetime.now(timezone.utc))
        path.write_text(json.dumps(bundle))
        print(json.dumps({'source_verification': stamps, 'run_id': bundle['run']['id'],
                          'source_files_written': 0, 'meta_posted': False}))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile):
        print('::warning::THREADS_SOURCE_PROOF_UNAVAILABLE; original freshness gates remain enforced')


if __name__ == '__main__':
    main()
