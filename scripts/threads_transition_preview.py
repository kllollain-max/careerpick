"""Isolated preflight adapter, never calls a publishing API.

This is not installed in threads_auto.py and has no side effects. The existing
publisher must explicitly integrate a reviewed adapter before any live use.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo
from scripts.threads_content_preview import generate, official_url

KST = ZoneInfo('Asia/Seoul')


def slot_from_cron(cron):
    # Use the triggering schedule rather than job start time, which can be late.
    slots = {'0 23 * * *': 8, '0 3 * * *': 12, '0 7 * * *': 16, '0 11 * * *': 20}
    if cron not in slots:
        raise ValueError('unknown schedule: no inferred slot')
    return slots[cron]


def validated_evidence(job, evidence, now):
    """Cross-check an independently sourced structured record; never fetches it.

    The caller must establish that evidence is authentic and from the named
    official source. This adapter cannot establish that by trusting a boolean.
    """
    if now.tzinfo is None or not isinstance(evidence, dict):
        raise ValueError('aware clock and source evidence required')
    if evidence.get('source') != 'ALIO official API' or not official_url(evidence.get('url')):
        raise ValueError('invalid official provenance')
    try:
        checked_at = datetime.fromisoformat(evidence['checked_at'])
        closes_at = datetime.fromisoformat(evidence['closes_at'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('timestamp evidence required') from exc
    if checked_at.tzinfo is None or closes_at.tzinfo is None:
        raise ValueError('timestamps require timezone')
    if checked_at > now or now - checked_at > timedelta(hours=24) or closes_at <= now:
        raise ValueError('stale evidence or closed')
    if evidence.get('status') != 'open' or evidence.get('revision_status') != 'current':
        raise ValueError('status or revision unknown')
    for key in ('org', 'title', 'qualification', 'count', 'location'):
        if evidence.get(key) in (None, '') or evidence.get(key) != job.get(key):
            raise ValueError('source field missing or differs: ' + key)
    if type(evidence['count']) is not int or evidence['count'] < 1:
        raise ValueError('invalid count')
    if not official_url(job.get('url')):
        raise ValueError('invalid job URL')
    source_id = parse_qs(urlsplit(evidence['url']).query).get('idx')
    if source_id != parse_qs(urlsplit(job['url']).query).get('idx'):
        raise ValueError('source URL differs')
    if closes_at.astimezone(KST).date().isoformat() != job.get('due'):
        raise ValueError('deadline differs')
    return dict(job, verified=True, evidence_source=evidence['source'], evidence_checked_at=checked_at.isoformat())


def prepare_content(*, enabled, cron, jobs, evidence_by_url, now, seed, legacy, previous_hooks=()):
    """Default legacy; enabled preflight declines invalid data without publishing."""
    if not enabled:
        return {'mode': 'legacy', 'content': legacy()}
    hour = slot_from_cron(cron)
    verified = []
    for job in jobs:
        try:
            verified.append(validated_evidence(job, evidence_by_url.get(job.get('url')), now))
        except (ValueError, TypeError, AttributeError):
            continue
    result = generate(hour, verified, now.astimezone(KST).date(), seed, previous_hooks)
    return {'mode': 'preview', 'content': result, 'evidence': [
        {'url': job['url'], 'source': job['evidence_source'], 'checked_at': job['evidence_checked_at']}
        for job in verified]}


def plan_media(*, image_url, image_ready, publish_state, text_valid):
    """Pre-publish planning only; never authorizes retry after an attempt."""
    if publish_state != 'not_started' or not text_valid:
        return 'hold'
    if image_url and image_ready:
        return 'image'
    return 'text'
