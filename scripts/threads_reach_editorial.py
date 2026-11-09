"""Reviewed first sentences that survive the compact publisher unchanged.

No requests, generated claims, mutations, or scheduling live here. Old immutable
queue entries retain their original rendering; the new contract is opt-in only
for their exact allowlisted hashes and mandatory for newly prepared entries.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import re

POLICY_ID = 'careerpick-threads-reach-v1-20261109'
GENERIC_HOOK = re.compile(r'채용정보\s*가져왔|취준생이라면\s*주목|좋은\s*기회예요|누구나\s*합격|무조건\s*지원|꿀직장|평생\s*안정|놓치면\s*손해')
EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF]')


def load_editorial_prompt(root, policy):
    config = policy.get('editorial_policy')
    if config is None:
        return None
    if config.get('id') != POLICY_ID or config.get('path') != 'threads/prompts/reach-v1.txt':
        raise ValueError('EDITORIAL_POLICY_CONTRACT')
    data = (root / config['path']).read_bytes()
    if hashlib.sha256(data).hexdigest() != config.get('sha256'):
        raise ValueError('EDITORIAL_POLICY_HASH_MISMATCH')
    return data.decode('utf-8')


def _fail(reason):
    from scripts.threads_writer_queue import QueueValidationError
    raise QueueValidationError(reason)


def _plain(text, limit=450):
    from scripts.threads_writer_queue import CTA, URL_RE, OTHER_ACTION_RE
    if (not isinstance(text, str) or not text or text != text.strip()
            or len(text) > limit or URL_RE.search(text) or '#' in text or '＃' in text
            or OTHER_ACTION_RE.search(text) or len(EMOJI.findall(text)) > 1
            or re.search(r'\*\*|```|__', text)):
        _fail('PUBLIC_COPY_CONTRACT')
    return text


def validate_reach(entry, policy, image, review, refs, detail):
    """Validate new editorial metadata after the ordinary official-source gates."""
    from scripts.threads_writer_queue import fingerprint, _evidence_supported, CTA, _fact_supported
    config = policy.get('editorial_policy')
    metadata = review.get('reach_editorial')
    if not config and metadata is None:
        return None
    if metadata is None:
        if fingerprint(entry) in config.get('grandfathered_entry_sha256', []):
            return None
        _fail('EDITORIAL_POLICY_REQUIRED')
    if (not config or entry.get('editorial_policy_id') != POLICY_ID
            or entry.get('editorial_policy_sha256') != config.get('sha256')
            or not isinstance(metadata, dict) or metadata.get('policy_id') != POLICY_ID):
        _fail('EDITORIAL_POLICY_MISMATCH')
    prepared = entry.get('prepared_at')
    try:
        prepared, effective = datetime.fromisoformat(prepared), datetime.fromisoformat(config['effective_at'])
        reference = datetime.fromisoformat(review['reference_at'])
        if (prepared.tzinfo is None or effective.tzinfo is None or reference.tzinfo is None
                or prepared < effective or prepared > reference):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        _fail('EDITORIAL_PREPARED_AT_INVALID')
    candidates = metadata.get('candidate_first_sentences')
    if not isinstance(candidates, list) or len(candidates) != 3:
        _fail('EDITORIAL_THREE_CANDIDATES_REQUIRED')
    ids, texts, types = set(), set(), set()
    chosen = None
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get('type') not in ('A', 'B', 'feature'):
            _fail('EDITORIAL_CANDIDATE_INVALID')
        text, cid = candidate.get('text'), candidate.get('id')
        _plain(text, 180)
        if '\n' in text or CTA in text or GENERIC_HOOK.search(text):
            _fail('EDITORIAL_HOOK_INVALID')
        if not isinstance(cid, str) or not cid or cid in ids or text in texts:
            _fail('EDITORIAL_CANDIDATE_DUPLICATE')
        ids.add(cid); texts.add(text); types.add(candidate['type'])
        if cid == metadata.get('selected_candidate_id'):
            chosen = candidate
    if types != {'A', 'B', 'feature'} or chosen is None or chosen['type'] not in ('A', 'B'):
        _fail('EDITORIAL_AB_SELECTION_REQUIRED')
    first = metadata.get('first_sentence')
    if first != chosen['text'] or metadata.get('hook_type') != chosen['type']:
        _fail('EDITORIAL_FINAL_HOOK_MISMATCH')
    # Both versions identify the actual institution and selected recruiting unit
    # in the very first line. Candidate B may lead with a grounded qualification.
    if image['org'] not in first or image['title'] not in first:
        _fail('EDITORIAL_FIRST_LINE_IDENTITY_REQUIRED')
    body = entry['writer']['post_text']
    if not body.startswith(first + '\n\n'):
        _fail('EDITORIAL_WRITER_HOOK_MISMATCH')
    _plain(body)
    if metadata.get('experiment_eligible') is not True:
        _fail('EDITORIAL_AB_ELIGIBILITY_REQUIRED')
    if not isinstance(metadata.get('selection_reason'), str) or not metadata['selection_reason'].strip():
        _fail('EDITORIAL_SELECTION_REASON_REQUIRED')
    # Explicit unit facts prevent a notice total silently becoming the count of
    # a narrower position, even if the two happen to have the same numeric value.
    scope = metadata.get('recruitment_unit')
    if not isinstance(scope, dict) or scope.get('title') != image['title']:
        _fail('EDITORIAL_RECRUITMENT_UNIT_REQUIRED')
    if scope.get('count') != image['count'] or scope.get('employment') != image['employment']:
        _fail('EDITORIAL_UNIT_FACT_CONFLICT')
    if image['count'] is not None and not _fact_supported('count', image['count'], review, refs, detail):
        _fail('EDITORIAL_UNIT_COUNT_EVIDENCE_REQUIRED')
    if image['count'] is not None and not any(
        fact.get('field') == 'count' and fact.get('value') == image['count']
        and ' '.join(image['title'].split()) in ' '.join(str(fact.get('excerpt', '')).split())
        and _fact_supported('count', image['count'], {'fact_evidence': [fact]}, refs, detail)
        for fact in review.get('fact_evidence', []) if isinstance(fact, dict)
    ):
        _fail('EDITORIAL_UNIT_COUNT_SCOPE_REQUIRED')
    if not _fact_supported('title', image['title'], review, refs, detail):
        _fail('EDITORIAL_UNIT_TITLE_EVIDENCE_REQUIRED')
    limitations = metadata.get('key_restrictions')
    if not isinstance(limitations, list) or metadata.get('restrictions_checked') is not True:
        _fail('EDITORIAL_RESTRICTIONS_REVIEW_REQUIRED')
    for item in limitations:
        if not isinstance(item, dict):
            _fail('EDITORIAL_RESTRICTION_INVALID')
        _plain(item.get('text'), 150)
        if '\n' in item['text'] or CTA in item['text'] or item['text'] not in body:
            _fail('EDITORIAL_RESTRICTION_COPY_MISMATCH')
        if not _evidence_supported(item.get('excerpt'), item.get('source_ref'), refs, detail):
            _fail('EDITORIAL_RESTRICTION_EVIDENCE_REQUIRED')
    result = deepcopy(metadata)
    main, reply = public_pair(body, image, result)
    preview = metadata.get('public_preview')
    if not isinstance(preview, dict) or preview.get('main_text') != main or preview.get('detail_reply') != reply:
        _fail('EDITORIAL_PUBLIC_PREVIEW_MISMATCH')
    # The review records human semantic checks; matching these flags does not
    # purport to prove facts from arbitrary prose automatically.
    if metadata.get('fact_consistency_check') != 'passed':
        _fail('EDITORIAL_PUBLIC_FACT_REVIEW_REQUIRED')
    return result


def public_pair(body, job, metadata):
    from scripts.threads_writer_queue import CTA
    first = metadata['first_sentence']
    count = f"{job['count']}명" if job['count'] is not None else '인원 미확인'
    lines = [first, f"고용·인원: {job['employment']} · {count}",
             f"근무: {job['location']}", f"접수 마감: {job['deadline_label']}"]
    lines += [item['text'] for item in metadata['key_restrictions']]
    main = '\n'.join(lines) + '\n\n' + CTA
    detail = body.removesuffix('\n\n' + CTA)
    if detail.startswith(first + '\n\n'):
        detail = detail[len(first) + 2:]
    _plain(main); _plain(detail)
    if main.count(CTA) != 1 or CTA in detail or not main.startswith(first + '\n'):
        _fail('EDITORIAL_PUBLIC_PAIR_INVALID')
    return main, detail


def balanced_hook_type(scheduled, start_date):
    """Counterbalance fixed slot/media parity over four calendar days.

    Successful media alternation may be disrupted by a failed slot; callers
    retain actual media and do not claim schedule alone balances the outcomes.
    """
    offset = (scheduled.date() - start_date).days
    slots = (8, 12, 16, 20)
    patterns = ('ABBA', 'BAAB', 'BAAB', 'ABBA')
    return patterns[offset % 4][slots.index(scheduled.hour)]
