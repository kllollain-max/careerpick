"""CareerPick single-main editorial contract. No network, scheduling or posting.

Contract v2 adds evidence-backed editorial metadata. These checks supplement the
writer's actual official-source review; they do not claim to understand every
legal eligibility sentence or prove factual correctness from a boolean flag.
"""
import hashlib
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

ID = 'careerpick-threads-v5-20261111'
CONTRACT_VERSION = 2
CTA = '자세한 사항은 프로필링크 확인'
STYLE = 'single_main_v5'
FORMATS = {'08':'hiring_core','12':'eligibility','16':'interest','20':'deadline_opportunity'}
KST = ZoneInfo('Asia/Seoul')
INTRO_TYPES = {'target', 'condition', 'deadline', 'job'}


def fail(code):
    from scripts.threads_writer_queue import QueueValidationError
    raise QueueValidationError('V5_' + code)


def load_prompt(root, policy):
    config = policy.get('editorial_v5')
    if not config:
        return None
    if config.get('id') != ID or config.get('path') != 'threads/prompts/reach-v5.txt':
        fail('CONFIG')
    data = (root / config['path']).read_bytes()
    if hashlib.sha256(data).hexdigest() != config.get('sha256'):
        fail('PROMPT_HASH')
    return data.decode('utf-8')


def entry_mode(entry, policy):
    config = policy.get('editorial_v5', {})
    if not isinstance(entry, dict):
        fail('ENTRY')
    is_new = entry.get('publication_policy_id') == ID
    if entry.get('writer', {}).get('review', {}).get('v5') and not is_new:
        fail('POLICY_REQUIRED')
    if not config.get('enabled'):
        if is_new:
            fail('NOT_ACTIVATED')
        return False
    from scripts.threads_writer_queue import fingerprint
    boundary=config.get('first_new_slot')
    if boundary is not None:
        try:
            first_slot=datetime.fromisoformat(boundary)
            entry_slot=datetime.fromisoformat(entry['scheduled_at'])
            if first_slot.tzinfo is None or entry_slot.tzinfo is None:
                raise ValueError
        except (KeyError,TypeError,ValueError):
            fail('CUTOVER_SLOT')
        if fingerprint(entry) in config.get('preserved_entry_sha256', []):
            if entry_slot>=first_slot:
                fail('FUTURE_ENTRY_CANNOT_BE_PRESERVED')
            return False
        if entry_slot<first_slot:
            fail('BEFORE_CUTOVER_SLOT')
    elif fingerprint(entry) in config.get('preserved_entry_sha256', []):
        return False
    if not is_new or entry.get('publication_policy_sha256') != config.get('sha256'):
        fail('POLICY_REQUIRED')
    try:
        activated = datetime.fromisoformat(config['effective_at'])
        prepared = datetime.fromisoformat(entry['prepared_at'])
        reference = datetime.fromisoformat(entry['writer']['review']['reference_at'])
        if any(x.tzinfo is None for x in [activated,prepared,reference]) or not activated <= prepared <= reference:
            raise ValueError
    except (ValueError,TypeError,KeyError):
        fail('ACTIVATION_OR_PREPARED_TIME')
    return True


def _linked(text):
    from scripts.threads_writer_queue import URL_RE
    folded = unicodedata.normalize('NFKC', text)
    folded = re.sub(r'[\u200b-\u200f\u2060\ufeff]', '', folded)
    folded = re.sub(r'\[(?:dot|점)\]|\((?:dot|점)\)', '.', folded, flags=re.I)
    return bool(URL_RE.search(folded) or re.search(
        r'(?:https?|hxxps?)\s*[:：]|www\s*\.|(?:[a-z0-9-]+\s*\.\s*)+[a-z]{2,63}(?:\b|/)',
        folded, re.I))


def _published(history):
    return sorted((r for r in history if isinstance(r, dict)
                   and r.get('status') == 'published' and r.get('threads_post_id')),
                  key=lambda r: str(r.get('published_at') or r.get('scheduled_at') or ''))


def copy_check(text, review, job, history=(), *, now=None):
    meta = review.get('v5', {})
    exception = meta.get('length_exception_reason')
    maximum = 350 if isinstance(exception, str) and exception.strip() else 300
    if not isinstance(text,str) or not text or text != text.strip() or len(text)>maximum:
        fail('LENGTH')
    if text.count(CTA)!=1 or not text.endswith('\n\n'+CTA):
        fail('CTA')
    if _linked(text) or re.search(r'[#＃]|\*\*|__|\x60\x60\x60', text):
        fail('LINK_OR_MARKUP')
    if re.search(r'(?<!\d)(?:1|2)\s*[/／]\s*2(?!\d)|이어서\s*(?:설명|안내)|다음\s*(?:댓글|답글)', text):
        fail('SPLIT_TRACE')
    if re.search(r'(댓글|저장|공유|리포스트|좋아요|DM|구독|맞팔)[^\n.!?]{0,24}(주세요|하세요|해요|남겨|눌러|교환)',text):
        fail('ENGAGEMENT_REQUEST')
    if re.search(r'무조건\s*합격|누구나\s*(?:지원|합격)|역대급|평생안정|꿀직장|놓치면.*손해|'
                 r'취준생\s*필독|안\s*보면\s*손해|이거\s*모르면\s*큰일|스펙\s*안\s*(?:봄|봐)|'
                 r'합격\s*(?:쉬워|쉬움|쉽)|경쟁률\s*낮|정년\s*보장',text):
        fail('UNSUPPORTED_HYPE')
    first=text.split('\n')[0]
    if any(str(r.get('text','')).split('\n')[0]==first for r in _published(history)[-8:]):
        fail('REPEATED_FIRST_LINE')
    lines=[x.strip() for x in text.removesuffix('\n\n'+CTA).split('\n') if x.strip()]
    if len(lines)!=len(set(lines)):
        fail('REPEATED_LINE')
    # A compact three-line fact group is allowed by the editorial instruction.
    if any(len(p.splitlines())>3 for p in text.split('\n\n')):
        fail('PARAGRAPH_LINES')
    for key in ['org','title','employment','location']:
        if job[key] not in text:
            fail('MISSING_'+key.upper())
    # The card keeps its canonical ISO label; public prose may use an exact
    # month/day rendering derived from that same source-verified timestamp.
    label=job['deadline_label']
    labels=[label]
    try:
        stamp=datetime.fromisoformat(label)
        clock=label.split(' ',1)[1]
        labels.append(f'{stamp.month}월 {stamp.day}일 {clock}')
    except (ValueError,TypeError,IndexError):
        pass
    if not any(re.search(re.escape(value)+r'(?![:0-9])',text) for value in labels):
        fail('MISSING_DEADLINE_LABEL')
    if job['count'] is not None and str(job['count'])+'명' not in text:
        fail('UNIT_COUNT')
    opening = '\n'.join(text.splitlines()[:2])
    if not (job['title'] in opening or
            (job['employment'] in opening and job['count'] is not None and str(job['count'])+'명' in opening) or
            (job['org'] in opening and re.search(r'지원|자격|경력|채용|모집|마감|뽑', opening))):
        fail('FIRST_TWO_LINES')
    # Relative words must be checked again against the actual pre-send KST time.
    if re.search(r'오늘|내일|D[-−]\d+', text, re.I):
        if now is None:
            fail('RELATIVE_DATE_NEEDS_CURRENT_TIME')
        try:
            current = now if isinstance(now, datetime) else datetime.fromisoformat(now)
            if current.tzinfo is None:
                raise ValueError
            days = (datetime.fromisoformat(job['due']).date()-current.astimezone(KST).date()).days
        except (TypeError, ValueError, KeyError):
            fail('RELATIVE_DATE_NEEDS_CURRENT_TIME')
        if ('오늘' in text and days != 0) or ('내일' in text and days != 1):
            fail('RELATIVE_DATE_CHANGED')
        if any(int(n) != days for n in re.findall(r'D[-−](\d+)',text,re.I)):
            fail('RELATIVE_DATE_CHANGED')
    emoji_count=len(re.findall(r'[\U0001f300-\U0001faff\u2600-\u27bf]',text))
    return {'chars':len(text),'recommended_length':150<=len(text)<=250,
            'length_exception_reason':exception if len(text)>300 else None,
            'emoji_count':emoji_count,'emoji_default_met':emoji_count<=1,
            'first_line_chars':len(first),'first_line_target_met':len(first)<=30,
            'recent_published_hooks_checked':min(8,len(_published(history)))}


def _evidence_item(item, body, refs, detail, code):
    from scripts.threads_writer_queue import _evidence_supported
    if (not isinstance(item, dict) or not isinstance(item.get('text'), str)
            or not item['text'].strip() or item['text'] not in body
            or not _evidence_supported(item.get('excerpt'),item.get('source_ref'),refs,detail)):
        fail(code)


def _restrictions(meta, body, refs, detail):
    from scripts.threads_writer_queue import _evidence_supported
    restrictions = meta.get('key_restrictions')
    if not isinstance(restrictions, list):
        fail('RESTRICTIONS_REQUIRED')
    for restriction in restrictions:
        _evidence_item(restriction,body,refs,detail,'RESTRICTION_EVIDENCE')
        text, excerpt = restriction['text'], restriction['excerpt']
        classification = restriction.get('classification')
        logic = restriction.get('logic')
        if classification not in {'required','preferred','bonus'} or logic not in {'single','any_of','all_of'}:
            fail('RESTRICTION_SEMANTICS')
        if classification in {'preferred','bonus'}:
            if re.search(r'필수|있어야|갖춰야|필요해요',text) and not re.search(r'필수.{0,8}(?:아니|아님)|필요하지',text):
                fail('PREFERENCE_AS_REQUIREMENT')
        # A direct graduation summary may not silently exclude expected graduates.
        if re.search(r'졸업\s*\(?예정|졸업예정',excerpt) and '졸업' in text and '예정' not in text:
            fail('EXPECTED_GRADUATES_OMITTED')
        paths=restriction.get('paths',[])
        if logic in {'any_of','all_of'}:
            if not isinstance(paths,list) or len(paths)<2:
                fail('RESTRICTION_PATHS_REQUIRED')
            for path in paths:
                if (not isinstance(path,dict) or not isinstance(path.get('summary'),str) or not path['summary'].strip()
                        or path['summary'] not in text
                        or not _evidence_supported(path.get('excerpt'),path.get('source_ref'),refs,detail)):
                    fail('RESTRICTION_PATH_EVIDENCE')
            if logic=='any_of':
                if not re.search(r'또는|이거나|하거나|중\s*(?:하나|한\s*가지)|인정\s*경로',text):
                    fail('ALTERNATIVE_LOGIC_LOST')
                if re.search(r'모두|동시에|거주자만|현재.{0,15}(?:주소|거주).{0,8}만',text):
                    fail('ALTERNATIVE_BECAME_CUMULATIVE')
            elif not re.search(r'모두|그리고|동시에|및|와|과|·',text):
                fail('CUMULATIVE_LOGIC_LOST')
    card = meta.get('card_restriction')
    if card is not None:
        if not isinstance(card,str) or not card.strip() or len(card)>42 or '\n' in card or _linked(card):
            fail('CARD_RESTRICTION')
        # It must be a verbatim, reviewed qualification phrase from the public body.
        if card not in body or not any(card in item['text'] for item in restrictions):
            fail('CARD_RESTRICTION_UNREVIEWED')


def _recruitment_unit(meta, job, refs, detail):
    """Tie a selected occupation's count to its retained official table row.

    This deliberately requires the first count following the selected title,
    so a later institution-wide total cannot stand in for that unit's count.
    The employment label is independently evidence-checked by validate_review.
    """
    from scripts.threads_writer_queue import _evidence_supported, _normal
    unit=meta.get('recruitment_unit')
    if (not isinstance(unit,dict) or unit.get('scope')!='single_recruitment_unit'
            or any(type(unit.get(k)) is not type(job.get(k)) or unit.get(k)!=job.get(k)
                   for k in ('title','count','employment'))
            or not _evidence_supported(unit.get('excerpt'),unit.get('source_ref'),refs,detail)):
        fail('RECRUITMENT_UNIT_EVIDENCE')
    excerpt=_normal(unit['excerpt'])
    title=_normal(job['title'])
    if title not in excerpt:
        fail('RECRUITMENT_UNIT_TITLE')
    if job['count'] is not None:
        after=excerpt.split(title,1)[1]
        # Prefer an explicit people count. A plain integer table cell is also
        # accepted when its complete ordered row is retained in the source.
        match=re.search(r'(?<!\d)([1-9][0-9]*)\s*명',after)
        if match is None:
            match=re.search(r'(?:^|[\s|/:：·])([1-9][0-9]*)(?=$|[\s|/·])',after)
        if match is None or int(match.group(1))!=job['count']:
            fail('UNIT_COUNT_BECAME_NOTICE_TOTAL')


def _salary_claims(meta, body, refs, detail):
    """Any numeric pay claim needs its own retained official evidence."""
    pattern=r'(?:연봉|월급|급여)(?:은|는|이|가|:|：)?\s*(?:약\s*|최대\s*|최소\s*)?[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:억|천|만)?\s*원?'
    claims=re.findall(pattern,body)
    if not claims:return
    evidence=meta.get('salary_claims',[])
    if not isinstance(evidence,list):fail('SALARY_EVIDENCE_REQUIRED')
    for item in evidence:
        _evidence_item(item,body,refs,detail,'SALARY_EVIDENCE_REQUIRED')
    normalized=lambda value:re.sub(r'[\s,]','',value)
    for claim in claims:
        if not any(claim in item['text'] and normalized(claim) in normalized(item['excerpt']) for item in evidence):
            fail('SALARY_EVIDENCE_REQUIRED')


def _hooks(meta, body):
    hooks=meta.get('hook_candidates')
    if not isinstance(hooks,list) or len(hooks)!=3:
        fail('THREE_HOOK_CANDIDATES_REQUIRED')
    if any(not isinstance(h,dict) or not isinstance(h.get('id'),str) or not h['id']
           or h.get('type') not in INTRO_TYPES or not isinstance(h.get('text'),str)
           or not h['text'].strip() or h['text']!=h['text'].strip() or len(h['text'].splitlines())>2
           or '\n\n' in h['text'] or _linked(h['text']) for h in hooks):
        fail('HOOK_CANDIDATE_INVALID')
    if len({h['id'] for h in hooks})!=3 or len({h['text'] for h in hooks})!=3:
        fail('HOOK_CANDIDATES_NOT_DISTINCT')
    selected=[h for h in hooks if h['id']==meta.get('selected_hook_id')]
    if len(selected)!=1 or selected[0]['text']!=body.split('\n\n')[0]:
        fail('SELECTED_HOOK_MISMATCH')
    if meta.get('first_sentence_type')!=selected[0]['type']:
        fail('HOOK_TYPE_MISMATCH')
    if meta.get('hook_review')!={'factual':True,'target_clear':True,'natural':True}:
        fail('HOOK_REVIEW_REQUIRED')


def _optional_sentences(meta, body, history, scheduled):
    value, question = meta.get('value_sentence'),meta.get('question')
    if value and question:
        fail('VALUE_AND_QUESTION_TOGETHER')
    for field, sentence in [('value_sentence',value),('question',question)]:
        if sentence is not None and (not isinstance(sentence,str) or not sentence.strip() or sentence not in body):
            fail('OPTIONAL_SENTENCE_MISMATCH')
    if '?' in body and not question:
        fail('QUESTION_METADATA_REQUIRED')
    if not value and not question:
        return
    try:
        slot=datetime.fromisoformat(scheduled)
        if slot.tzinfo is None: raise ValueError
        day=slot.astimezone(KST).date()
    except (TypeError,ValueError):
        fail('OPTIONAL_SENTENCE_DAY')
    for record in history:
        if record.get('status') not in {'published','pending'}:continue
        prior=record.get('writer_review',{}).get('v5',{})
        try:
            at=datetime.fromisoformat(record.get('published_at') or record.get('scheduled_at'))
            same_day=at.tzinfo is not None and at.astimezone(KST).date()==day
        except (TypeError,ValueError):continue
        if same_day and ((value and prior.get('value_sentence')) or (question and prior.get('question'))):
            fail('OPTIONAL_SENTENCE_DAILY_LIMIT')


def validate_review(entry, job, review, refs, detail, history, *, now=None):
    from scripts.threads_writer_queue import _fact_supported,_evidence_supported,_ref_id
    meta=review.get('v5',{})
    if (meta.get('policy_id')!=ID or meta.get('contract_version')!=CONTRACT_VERSION
            or meta.get('restrictions_complete') is not True or meta.get('fact_consistency_check')!='passed'):
        fail('SEMANTIC_REVIEW')
    body=entry['writer']['post_text']
    checks=copy_check(body,review,job,history['records'],now=now)
    _hooks(meta,body)
    _restrictions(meta,body,refs,detail)
    _recruitment_unit(meta,job,refs,detail)
    _salary_claims(meta,body,refs,detail)
    _evidence_item(meta.get('useful_point'),body,refs,detail,'USEFUL_POINT_EVIDENCE')
    for field in ['title','count','employment','location']:
        if job[field] is not None and not _fact_supported(field,job[field],review,refs,detail):
            fail('FACT_EVIDENCE_'+field.upper())
    correction=meta.get('correction_check')
    if (not isinstance(correction,dict) or correction.get('result') not in {'none_found','reviewed_applied'}
            or correction.get('source_ref') not in {_ref_id(ref) for ref in refs}):
        fail('CORRECTION_CHECK_REQUIRED')
    try:
        checked=datetime.fromisoformat(correction['checked_at'])
        reference=datetime.fromisoformat(review['reference_at'])
        original=datetime.fromisoformat(review['checked_at'])
        if any(x.tzinfo is None for x in (checked,reference,original)) or not original<=checked<=reference:
            raise ValueError
    except (KeyError,TypeError,ValueError):
        fail('CORRECTION_CHECK_TIME')
    if type(meta.get('style_rewrites')) is not int or not 0<=meta['style_rewrites']<=2:
        fail('STYLE_REWRITE_LIMIT')
    if meta.get('public_preview')!={'main_text':body,'detail_reply':''}:
        fail('PREVIEW')
    if not isinstance(meta.get('selection_reason'),str) or not meta['selection_reason'].strip():
        fail('SELECTION_REASON')
    _optional_sentences(meta,body,history['records'],entry.get('scheduled_at') or review.get('scheduled_at'))
    # Explicitly preserve official deadline precision; unknown closing time is a hold.
    if review.get('application_period',{}).get('date_only') is not False:
        fail('DEADLINE_TIME_REQUIRED')
    return checks


def balanced_intro_type(scheduled, history, media):
    """Balance target/condition within slot+media; never duplicate a job to test."""
    at=scheduled if isinstance(scheduled,datetime) else datetime.fromisoformat(scheduled)
    if at.tzinfo is None or media not in {'IMAGE','TEXT'}:
        fail('EXPERIMENT_CONTEXT')
    hour=at.astimezone(KST).hour
    per_arm={arm:[0,0] for arm in ('target','condition')}
    for record in history:
        if record.get('status') not in {'published','pending'}:continue
        meta=record.get('writer_review',{}).get('v5',{})
        arm=meta.get('first_sentence_type')
        if (arm not in per_arm or meta.get('contract_version')!=CONTRACT_VERSION
                or meta.get('experiment_eligible') is False):continue
        try:
            prior=datetime.fromisoformat(record['scheduled_at']).astimezone(KST)
        except (KeyError,ValueError,TypeError):continue
        per_arm[arm][1]+=1
        actual='IMAGE' if record.get('image_url') else 'TEXT'
        if prior.hour==hour and actual==media:per_arm[arm][0]+=1
    # Alternate the initial tie across days and slots; neither arm is a fixed hour.
    tie=('target','condition') if (at.astimezone(KST).date().toordinal()+hour//4)%2==0 else ('condition','target')
    return min(tie,key=lambda arm:tuple(per_arm[arm]))


def ranking_key(row, now=None, history=()):
    """Source-review order: no invented institution popularity or sector bias."""
    interest=row.get('interest')
    score=0
    if (isinstance(interest,dict) and interest.get('verified') is True
            and isinstance(interest.get('observation_ids'),list) and interest['observation_ids']
            and type(interest.get('score')) in (int,float)):
        score=interest['score']
    count=row.get('unit_count')
    count=count if type(count) is int and count>0 and row.get('unit_scope')=='reviewed_unit' else None
    period=row['application_period']['end']
    preparation=1
    if now is not None:
        try:
            end=datetime.fromisoformat(period)
            if end.tzinfo is None:end=end.replace(tzinfo=KST)
            current=now if isinstance(now,datetime) else datetime.fromisoformat(now)
            # A review-order heuristic, not a platform or eligibility threshold.
            preparation=0 if (end-current).total_seconds()>=48*3600 else 1
        except (ValueError,TypeError):pass
    recent=_published(history)[-8:]
    repetition=sum(r.get('image_job',{}).get('org')==row.get('org') for r in recent if isinstance(r.get('image_job'),dict))
    advantage=0 if row.get('verified_advantages') else 1
    return (-score,row['employment_priority'],count is None,-(count or 0),advantage,
            preparation,repetition,period,row['notice_id'])


def generate_card(job, destination):
    from scripts.create_thumbnail import generate_compact_card
    return generate_compact_card(job,destination)


def performance_summary(history, state, now):
    """Compatibility entry point for the operational 24h/72h report."""
    from scripts.threads_performance import v5_performance_summary
    return v5_performance_summary(history, state, now)
