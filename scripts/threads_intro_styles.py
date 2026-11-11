"""Read-only editorial planning; never consumes media turns or publishes."""
import hashlib
from datetime import datetime

STYLES = ('regular_interest', 'eligibility_info')


def load_guidance(root, policy):
    config = policy.get('intro_style_policy', {})
    if not config.get('enabled'):
        return None
    if config.get('path') != 'threads/prompts/intro-styles-v2-20261111.txt':
        raise ValueError('INTRO_STYLE_PATH')
    data = (root / config['path']).read_bytes()
    if hashlib.sha256(data).hexdigest() != config.get('sha256'):
        raise ValueError('INTRO_STYLE_HASH')
    return data.decode('utf-8')


def plan_styles(slots, history, config):
    if not config.get('enabled'):
        return
    first = datetime.fromisoformat(config['first_new_slot'])
    if first.tzinfo is None:
        raise ValueError('INTRO_STYLE_TIMEZONE')
    prior = None
    for record in history:
        if record.get('status') != 'published' or not record.get('threads_post_id'):
            continue
        meta = record.get('writer_review', {}).get('v5', {})
        if meta.get('contract_version') != 2:
            continue
        style = meta.get('presentation_style')
        if style not in STYLES:
            style = {'target':STYLES[0], 'condition':STYLES[1]}.get(meta.get('first_sentence_type'))
        if style in STYLES:
            prior = style
    next_style = STYLES[0] if prior != STYLES[0] else STYLES[1]
    for slot in slots:
        at = datetime.fromisoformat(slot['scheduled_at'])
        if at.tzinfo is None:
            raise ValueError('INTRO_STYLE_TIMEZONE')
        if at < first:
            continue
        slot['presentation_style'] = next_style
        slot['presentation_style_planning_only'] = True
        next_style = STYLES[1] if next_style == STYLES[0] else STYLES[0]
