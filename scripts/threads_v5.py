"""Staged v5 editorial contract. No network, scheduling or posting."""
import hashlib
import re
from datetime import datetime

ID = 'careerpick-threads-v5-20261111'
CTA = '자세한 사항은 프로필링크 확인'
STYLE = 'single_main_v5'
FORMATS = {'08':'hiring_core','12':'eligibility','16':'interest','20':'deadline_opportunity'}
SECTORS = {'energy_power':0,'rail_transport_logistics':1,'finance_insurance_pension':2,'other':3,'hospital_health':5}


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
    if fingerprint(entry) in config.get('preserved_entry_sha256', []):
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


def copy_check(text, review, job, history=()):
    from scripts.threads_writer_queue import URL_RE
    multi = review.get('v5', {}).get('verified_multiple_units', [])
    maximum = 350 if len(multi) >= 2 and review['v5'].get('multi_role_justification') else 300
    if not isinstance(text,str) or not text or text != text.strip() or len(text)>maximum:
        fail('LENGTH')
    if text.count(CTA)!=1 or not text.endswith('\n\n'+CTA):
        fail('CTA')
    if URL_RE.search(text) or re.search(r'[#＃]|\*\*|__|\x60\x60\x60', text):
        fail('LINK_OR_MARKUP')
    if re.search(r'(댓글|저장|공유|리포스트|좋아요|DM|구독)[^\n.!?]{0,24}(주세요|하세요|해요|남겨|눌러)',text):
        fail('ENGAGEMENT_REQUEST')
    if re.search(r'무조건|누구나.*합격|역대급|평생안정|꿀직장|놓치면.*손해',text):
        fail('UNSUPPORTED_HYPE')
    first=text.split('\n')[0]
    if any(str(r.get('text','')).split('\n')[0]==first for r in list(history)[-10:]):
        fail('REPEATED_FIRST_LINE')
    lines=[x.strip() for x in text.removesuffix('\n\n'+CTA).split('\n') if x.strip()]
    if len(lines)!=len(set(lines)):
        fail('REPEATED_LINE')
    if any(len(p.splitlines())>2 for p in text.split('\n\n')):
        fail('PARAGRAPH_LINES')
    for key in ['org','title','employment','location','deadline_label']:
        if job[key] not in text:
            fail('MISSING_'+key.upper())
    if job['count'] is not None and str(job['count'])+'명' not in text:
        fail('UNIT_COUNT')
    if job['org'] not in '\n'.join(text.splitlines()[:2]):
        fail('FIRST_TWO_LINES')
    return {'chars':len(text),'recommended_length':150<=len(text)<=250,
            'first_line_chars':len(first),'first_line_target_met':len(first)<=30}


def validate_review(entry, job, review, refs, detail, history):
    from scripts.threads_writer_queue import _fact_supported,_evidence_supported
    meta=review.get('v5',{})
    if meta.get('policy_id')!=ID or meta.get('restrictions_complete') is not True or meta.get('fact_consistency_check')!='passed':
        fail('SEMANTIC_REVIEW')
    body=entry['writer']['post_text']
    checks=copy_check(body,review,job,history['records'])
    if not isinstance(meta.get('key_restrictions'),list):
        fail('RESTRICTIONS_REQUIRED')
    for restriction in meta['key_restrictions']:
        if restriction.get('text') not in body or not _evidence_supported(restriction.get('excerpt'),restriction.get('source_ref'),refs,detail):
            fail('RESTRICTION_EVIDENCE')
    for field in ['title','count','employment','location']:
        if job[field] is not None and not _fact_supported(field,job[field],review,refs,detail):
            fail('FACT_EVIDENCE_'+field.upper())
    for unit in meta.get('verified_multiple_units',[]):
        if not _evidence_supported(unit.get('excerpt'),unit.get('source_ref'),refs,detail):
            fail('MULTI_UNIT_EVIDENCE')
    if meta.get('public_preview')!={'main_text':body,'detail_reply':''}:
        fail('PREVIEW')
    if not meta.get('selection_reason'):
        fail('SELECTION_REASON')
    return checks


def ranking_key(row):
    # User sector preference, never measured popularity. Unknown counts stay null.
    period=row['application_period']['end']
    return (SECTORS.get(row.get('sector_group'),3),row['employment_priority'],
            row['unit_count'] is None,-(row['unit_count'] or 0),period,row['notice_id'])


def generate_card(job, destination):
    """Reuse the clipping/glyph/byte guards, with a shorter text-only layout."""
    from PIL import Image, ImageDraw
    from scripts.create_thumbnail import _draw_fitted, verify_thumbnail
    from pathlib import Path
    im=Image.new('RGB',(1080,1080),'#F2F8FF'); draw=ImageDraw.Draw(im)
    draw.rounded_rectangle((48,45,1032,157),radius=22,fill='#132B4E')
    def fitted(text,box,size,lines=2,fill='#132B4E'):
        _draw_fitted(draw,text,box,size=size,minimum=38,max_lines=lines,fill=fill)
    fitted('CAREERPICK  |  채용정보',(78,65,1002,137),44,1,'white')
    fitted(job['org'],(70,205,1010,390),80,2)
    fitted(job['title'],(70,420,1010,620),76,3)
    count=str(job['count'])+'명' if job['count'] is not None else '인원 공고 확인'
    draw.rounded_rectangle((48,690,1032,1000),radius=25,fill='white')
    fitted(job['employment']+' · '+count,(84,720,996,800),54,2)
    fitted('접수마감 '+job['deadline_label'],(84,840,996,950),48,2)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile(dir=destination.parent,suffix='.jpg',delete=False) as handle:
        temporary=Path(handle.name)
    try:
        im.save(temporary,'JPEG',quality=95,subsampling=0)
        quality=verify_thumbnail(temporary)
        temporary.replace(destination)
        return quality
    finally:
        temporary.unlink(missing_ok=True)


def performance_summary(history, state, now):
    """Describe only verified v5 main posts at matched ages, never infer clicks."""
    from collections import Counter, defaultdict
    from statistics import median
    from scripts.threads_performance import moment, _review
    now=moment(now)
    records={str(r.get('threads_post_id')):r for r in history.get('records',[])
             if r.get('status')=='published' and _review(r).get('v5',{}).get('policy_id')==ID}
    excluded=Counter();windows={label:[] for label in ('24h','72h')};seen=set()
    for observation in state.get('observations',[]):
        post_id=observation.get('post_id');record=records.get(post_id)
        if record is None:continue
        label=observation.get('window')
        if label not in windows:continue
        try:
            published=moment(record['published_at']);captured=moment(observation['captured_at'])
        except (KeyError,TypeError,ValueError):
            excluded['invalid_time']+=1;continue
        if not 0 <= (now-published).total_seconds() <= 28*86400 or captured>now:
            excluded['outside_time_window']+=1;continue
        age=86400 if label=='24h' else 72*3600
        elapsed=(captured-published).total_seconds()
        if not age<=elapsed<=age+3600 or observation.get('status')!='captured':
            excluded['late_or_unavailable']+=1;continue
        proof=observation.get('public_verification') or {}
        expected=hashlib.sha256(str(record.get('text','')).encode()).hexdigest()
        if (proof.get('status')!='verified' or proof.get('post_id')!=post_id
                or proof.get('actual_text_sha256')!=expected
                or proof.get('expected_text_sha256')!=expected or proof.get('is_reply') is not False):
            excluded['public_main_unverified']+=1;continue
        if (post_id,label) in seen:continue
        seen.add((post_id,label))
        values={k:v if type(v) is int and v>=0 else None
                for k,v in observation.get('metrics',{}).items()}
        views=values.get('views')
        response=[values.get(k) for k in ('likes','reposts','quotes')]
        rate=(sum(response)/views if views and all(x is not None for x in response) else None)
        meta=_review(record)['v5']
        windows[label].append({'post_id':post_id,'metrics':values,'elapsed_seconds':elapsed,
            'response_rate_likes_reposts_quotes':rate,'reader_replies':observation.get('reader_replies'),
            'format_id':record.get('format_id'),'first_sentence_type':meta.get('first_sentence_type'),
            'sector_group':meta.get('sector_group'),'body_chars':len(record.get('text','')),
            'media':'IMAGE' if record.get('image_url') else 'TEXT','slot':record.get('scheduled_at')})
    def stats(items):
        keys=('views','likes','replies','reposts','quotes')
        medians={k:median(v) if (v:=[x['metrics'].get(k) for x in items
                     if x['metrics'].get(k) is not None]) else None for k in keys}
        rates=[x['response_rate_likes_reposts_quotes'] for x in items
               if x['response_rate_likes_reposts_quotes'] is not None]
        return {'verified_main_count':len(items),'metric_medians':medians,
                'median_response_rate_likes_reposts_quotes':median(rates) if rates else None,
                'reader_replies':None,'profile_visits':None,'follow_increase':None,'link_clicks':None}
    return {'policy_id':ID,'windows':{label:stats(rows) for label,rows in windows.items()},
        'observations':windows,'excluded':dict(excluded),'automatic_weight_changes':0,
        'decision':'keep_current_weights_until_comparable_repeated_evidence',
        'limitations':['No post-attributed follow/profile/click API values supplied',
                       'Likes+reposts+quotes rate is not unique-reader engagement',
                       'Sector, unit scope, slot, format and media remain confounded',
                       'Do not combine this cohort with legacy A/B results']}
