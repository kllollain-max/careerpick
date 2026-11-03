#!/usr/bin/env python3
"""Validate a complete candidate in isolation. Never publish or send notifications."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alio
from scripts.collect_alio import collect
ROOT = Path(__file__).resolve().parents[1]
NAMES = ('alio.json', 'alio-detail.json')


def stamp():
    return datetime.now(alio.KST).isoformat(timespec='seconds')


def validate(feed, details):
    if not isinstance(feed, dict) or not isinstance(feed.get('posts'), list) or not feed['posts']:
        raise ValueError('empty_or_invalid_feed')
    ids = set()
    for p in feed['posts']:
        identity = p.get('id', '')
        if identity in ids or not identity.startswith('a') or not identity[1:].isdigit():
            raise ValueError('duplicate_or_invalid_identity')
        ids.add(identity)
        d = details.get(identity)
        if not isinstance(d, dict) or str(d.get('recrutPblntSn')) != identity[1:]:
            raise ValueError('detail_missing_or_mismatch')
        if not p.get('title') or not p.get('org') or not p.get('url', '').startswith('https://job.alio.go.kr/'):
            raise ValueError('missing_required_fields')
        for name in ('pub', 'due'):
            if p.get(name):
                value = datetime.fromisoformat(p[name])
                if value.tzinfo is None:
                    raise ValueError('timezone_missing')
        if p.get('due') and p.get('pub') and datetime.fromisoformat(p['due']) < datetime.fromisoformat(p['pub']):
            raise ValueError('inverted_application_dates')
    return ids


def state(p, now):
    if p.get('due') and datetime.fromisoformat(p['due']) < now:
        return 'archived'
    if p.get('pub') and datetime.fromisoformat(p['pub']) > now:
        return 'upcoming'
    if p.get('due') or p.get('always'):
        return 'open'
    return 'unknown'


def metrics(before, after, old_details, new_details, now):
    old = {p['id']: p for p in before['posts']}
    new = {p['id']: p for p in after['posts']}
    common = old.keys() & new.keys()
    return dict(before=len(old), new=len(new.keys()-old.keys()),
                modified=sum(old[i] != new[i] or old_details.get(i) != new_details.get(i) for i in common),
                ended=sum(state(old[i], datetime.fromisoformat(before['updated'])) != 'archived' and state(new[i], now) == 'archived' for i in common),
                archive_transitions=sum(state(old[i], datetime.fromisoformat(before['updated'])) != 'archived' and state(new[i], now) == 'archived' for i in common),
                deleted=len(old.keys()-new.keys()), after=len(new),
                **{s: sum(state(p, now) == s for p in new.values()) for s in ('open', 'upcoming', 'archived', 'unknown')})


def run(root=ROOT, collector=collect, detail_call=None):
    output = root / 'operations-output'
    output.mkdir(exist_ok=True)
    originals = {n: (root/n).read_bytes() for n in NAMES}
    before, old_details = [json.loads(originals[n]) for n in NAMES]
    validate(before, old_details)
    report = dict(started_at=stamp(), source='alio', collection='not_started', validation='not_started', storage='not_started', deployment='not_requested', changed=False,
                  source_snapshot_at=before['updated'], source_hashes={n: hashlib.sha256(v).hexdigest() for n,v in originals.items()})
    try:
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder)
            for n,b in originals.items(): (stage/n).write_bytes(b)
            result = collector(stage)
            if result['status'] != 'collected':
                raise ValueError('collection_not_successful')
            report['collection'] = 'success'
            after, details = [json.loads((stage/n).read_bytes()) for n in NAMES]
            ids = validate(after, details)
            if not {p['id'] for p in before['posts']} <= ids:
                raise ValueError('existing_ids_lost')
            previous = root/'operations-status.json'
            prev = json.loads(previous.read_text()) if previous.exists() else {}
            received = result['received']
            # An unexpectedly large decrease needs review, even though archives are retained.
            baseline = prev.get('last_received', 509)
            if received < max(1, int(baseline * .7)):
                raise ValueError('unexpected_collection_decrease')
            # List carries detail fields; also validate current detail endpoint sample.
            if detail_call is not None:
                sampled = [p for p in after['posts'] if state(p, datetime.now(alio.KST)) == 'open'][:3]
                for p in sampled:
                    d = detail_call(p['id'][1:])
                    if str(d.get('recrutPblntSn')) != p['id'][1:]:
                        raise ValueError('live_detail_mismatch')
                report['live_details_verified'] = len(sampled)
            report['counts'] = metrics(before, after, old_details, details, datetime.now(alio.KST))
            received_ids = set(result.get('received_ids', []))
            uncertain = sorted(p['id'] for p in after['posts'] if state(p, datetime.now(alio.KST)) in ('open','upcoming') and p['id'] not in received_ids)
            report['counts']['confirmed_current'] = sum(p['id'] in received_ids and state(p, datetime.now(alio.KST)) == 'open' for p in after['posts'])
            report['counts']['unconfirmed'] = len(uncertain)
            report.update(validation='success', verified_at=stamp(), changed=result['changed'], snapshot_at=after['updated'])
            candidate = output/'candidate'
            candidate.mkdir(exist_ok=True)
            for n in NAMES: shutil.copyfile(stage/n, candidate/n)
            status = dict(source='alio', last_success_at=report['verified_at'], snapshot_at=after['updated'], last_received=received, unconfirmed_ids=uncertain, counts=report['counts'])
            (candidate/'operations-status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
            report['storage'] = 'candidate_validated'
    except Exception as error:
        # No exception strings or request/response bodies leave this boundary.
        report.update(error_type=type(error).__name__, status='failed_preserved', changed=False)
    else:
        report['status'] = 'changed' if report['changed'] else 'unchanged'
    report['originals_preserved'] = all((root/n).read_bytes() == b for n,b in originals.items())
    report['finished_at'] = stamp()
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
    return report

if __name__ == '__main__':
    result=run(detail_call=lambda sn: alio.call_detail(os.environ.get('ALIO_KEY',''),sn))
    sys.exit(0 if result['status'] in ('changed','unchanged') else 1)
