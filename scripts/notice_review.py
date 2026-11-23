"""Identity-bound editorial comparisons of official notice originals.

Never infer duplicate recruitment from a title, attachment filename or job template.
A changed/missing member invalidates the entire comparison until re-reviewed.
"""
import hashlib
import json
import re
from pathlib import Path

POST_FIELDS = ('id', 'alio', 'org', 'title', 'n', 'emp', 'edu', 'region', 'pub', 'due', 'dueHasTime', 'src')
DETAIL_FIELDS = ('recrutPblntSn', 'aplyQlfcCn', 'scrnprcdrMthdExpln', 'prefCn', 'prefCondCn', 'workRgnNmLst', 'hireTypeNmLst', 'acbgCondNmLst', 'recrutNope', 'disqlfcRsn', 'srcUrl')

def fingerprint(post, detail):
    payload = [{k: post.get(k) for k in POST_FIELDS}, {k: detail.get(k) for k in DETAIL_FIELDS}]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def resolve(posts, details, rules=None):
    if rules is None:
        rules = json.loads(Path(__file__).with_name('verified_notice_reviews.json').read_text())
    by_id = {p.get('id'): p for p in posts}
    result = {}
    used = set()
    for rule in rules:
        members = rule.get('members', [])
        ids = [m.get('id', '') for m in members]
        if len(ids) < 2 or len(set(ids)) != len(ids) or used.intersection(ids):
            continue
        if any(not re.fullmatch(r'a[0-9]+', pid) for pid in ids):
            continue
        if rule.get('decision') not in ('same_notice', 'distinct_notice', 'amended_notice'):
            continue
        representative = rule.get('representative_id')
        if (rule['decision'] == 'same_notice' or
                (rule['decision'] == 'amended_notice' and representative is not None)) and representative not in ids:
            continue
        if any(pid not in by_id or not isinstance(details.get(pid), dict) or
               fingerprint(by_id[pid], details[pid]) != member.get('fingerprint')
               for pid, member in zip(ids, members)):
            continue
        # Same-notice decisions require both the notice AND duties originals
        # to have identical verified bytes, not merely matching API summaries.
        proofs = [m.get('sources', []) for m in members]
        if any(len(p) not in (1, 2) or any(not re.fullmatch(r'[a-f0-9]{64}', s.get('sha256', ''))
               or not re.fullmatch(r'https://www.alio.go.kr/download/download.json\?fileNo=[0-9]+', s.get('url', '')) for s in p) for p in proofs):
            continue
        if rule['decision'] == 'same_notice' and (any(len(p) != 2 for p in proofs) or len({tuple(s['sha256'] for s in p) for p in proofs}) != 1):
            continue
        # A revised group may contain an unchanged duplicate pair alongside
        # a genuinely amended notice. Keep that old verified canonical only
        # when BOTH originals and the relevant source terms still match.
        aliases = {m['id']: m['same_source_representative'] for m in members
                   if m.get('same_source_representative') is not None}
        by_member = {m['id']: m for m in members}
        if aliases and (rule['decision'] != 'amended_notice' or any(
                target not in ids or target == pid or target in aliases
                or len(by_member[pid]['sources']) != 2
                or len(by_member.get(target, {}).get('sources', [])) != 2
                or tuple(x['sha256'] for x in by_member[pid]['sources']) !=
                   tuple(x['sha256'] for x in by_member[target]['sources'])
                or any(by_id[pid].get(k) != by_id[target].get(k)
                       for k in ('org', 'title', 'n', 'emp', 'due'))
                for pid, target in aliases.items())):
            continue
        used.update(ids)
        for member in members:
            result[member['id']] = dict(member,
                decision='same_notice' if member['id'] in aliases else rule['decision'],
                representative_id=aliases.get(member['id'], representative), checked_on=rule['checked_on'], peer_ids=ids,
                publish_note=rule.get('publish_note', True))
    return result

def load(root):
    try:
        posts = json.loads((root / 'alio.json').read_text()).get('posts', [])
        details = json.loads((root / 'alio-detail.json').read_text())
    except (OSError, ValueError, AttributeError):
        return {}
    return resolve(posts, details)
