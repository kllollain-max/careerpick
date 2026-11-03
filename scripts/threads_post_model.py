"""Offline post-work schema. No publication or legacy history mutation.

Evidence and source authenticity remain the caller's responsibility; these
structures alone do not authorize a live request.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit
import json

KINDS = {'job', 'discussion', 'tip', 'comparison'}


def _valid_url(value):
    try:
        p = urlsplit(value)
        return p.scheme == 'https' and p.hostname == 'job.alio.go.kr' and not p.username and not p.password and p.port in (None, 443)
    except (TypeError, ValueError):
        return False


def _verified_job(j):
    if not isinstance(j, dict) or j.get('verified') is not True:
        raise ValueError('source verification required')
    for field in ('id', 'org', 'title', 'due', 'url'):
        if not isinstance(j.get(field), str) or not j[field].strip():
            raise ValueError('missing job ' + field)
    if not _valid_url(j['url']):
        raise ValueError('invalid official URL')
    return j


@dataclass(frozen=True)
class PostWork:
    task_id: str
    kind: str
    content_hash: str
    scheduled_at: str
    status: str
    threads_post_id: str | None
    job_ids: tuple
    use_image: bool
    request_status: str
    body: str
    replies: tuple


def build_work(kind, scheduled_at, body, jobs=(), reply_notes=(), use_image=False):
    if kind not in KINDS or not isinstance(scheduled_at, datetime) or scheduled_at.tzinfo is None:
        raise ValueError('invalid kind or schedule')
    if not isinstance(body, str) or not body.strip() or len(body) > 500 or type(use_image) is not bool:
        raise ValueError('invalid body or media')
    jobs = tuple(jobs)
    if kind in ('discussion', 'tip') and jobs:
        raise ValueError('non-job content cannot carry jobs')
    if kind in ('job', 'comparison') and not jobs:
        raise ValueError('job evidence required')
    if kind == 'job' and len(jobs) != 1:
        raise ValueError('job post must reference one job')
    jobs = tuple(_verified_job(j) for j in jobs)
    ids = tuple(j['id'] for j in jobs)
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate jobs')
    if any(not isinstance(x, str) or not x.strip() or len(x) > 500 for x in reply_notes):
        raise ValueError('invalid notes')
    replies = tuple(reply_notes)
    if jobs:
        for j in jobs:
            reply = j['org'] + ' · ' + j['title'] + '\n' + j['url']
            if len(reply) > 500:
                raise ValueError('official reply too long')
            replies += (reply,)
    digest = sha256(body.encode('utf-8')).hexdigest()
    # One slot permits one post, regardless of content type or timezone spelling.
    identity = json.dumps([scheduled_at.astimezone(timezone.utc).isoformat()], separators=(',', ':'))
    task_id = sha256(identity.encode()).hexdigest()
    return PostWork(task_id, kind, digest, scheduled_at.isoformat(), 'prepared', None,
                    ids, use_image, 'not_started', body, replies)


def assert_safe_to_reserve(work, history):
    """Check both old and new records conservatively. Does not persist a claim."""
    for record in history.get('records', []):
        if record.get('status') in ('pending', 'uncertain'):
            raise ValueError('unresolved reservation')
        if record.get('task_id') == work.task_id or record.get('content_hash') == work.content_hash:
            raise ValueError('duplicate content or slot')
        legacy_id = record.get('job_id')
        ids = list(record.get('job_ids') or []) + ([legacy_id] if legacy_id else [])
        if set(ids).intersection(work.job_ids):
            raise ValueError('job already reserved')
    if set(history.get('posted_ids', [])).intersection(work.job_ids):
        raise ValueError('legacy job already posted')


def record_receipt(work, post_id):
    if not isinstance(post_id, str) or not post_id.isdigit():
        raise ValueError('unconfirmed response')
    result = asdict(work)
    result.update(status='published', request_status='confirmed', threads_post_id=post_id)
    return result


def work_from_preview(preview, scheduled_at, verified_jobs=(), use_image=False):
    """Translate a preview into a typed record; fails on ambiguous job selection."""
    if not isinstance(preview, dict):
        raise ValueError('preview required')
    kind_map = {'job': 'job', 'conversation': 'discussion', 'tips': 'tip', 'strategy': 'comparison'}
    kind = kind_map.get(preview.get('type'))
    jobs = tuple(verified_jobs)
    if kind is None:
        raise ValueError('unsupported preview type')
    if kind in ('discussion', 'tip'):
        jobs = ()
    elif len(jobs) != 1:
        # The current generator omits the selected source ID, so do not guess.
        raise ValueError('exactly one source job required')
    if jobs:
        body = preview.get('body')
        if not isinstance(body, str) or any(str(jobs[0].get(key, '')) not in body for key in ('org', 'title', 'due', 'url')):
            raise ValueError('preview does not match source job')
    return build_work(kind, scheduled_at, preview.get('body'), jobs, use_image=use_image)
