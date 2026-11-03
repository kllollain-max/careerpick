#!/usr/bin/env python3
"""CareerPick Threads publisher, diagnostics and explicit receipt recovery."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Direct script execution must also resolve the repository's scripts package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts.threads_editorial import enrich_main, engagement, validated_reply, conversation_main
except ModuleNotFoundError:
    from threads_editorial import enrich_main, engagement, validated_reply, conversation_main

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'alio.json'
HISTORY = ROOT / 'threads_posted.json'

KST = ZoneInfo('Asia/Seoul')
API = 'https://graph.threads.net/v1.0'

MIN_DAYS = 5
MAX_DAYS = 20
MAX_DAILY = 4


def load(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save(data):
    HISTORY.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8'
    )


def parse_date(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).strip().replace('Z', '+00:00')
        )
        return dt.astimezone(KST).date() if dt.tzinfo else dt.date()
    except (ValueError, TypeError):
        try:
            return date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError):
            return None


def parse_count(value):
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value if value >= 0 else None

    if isinstance(value, str):
        cleaned = value.strip().replace(',', '')
        if re.fullmatch(r'\d+', cleaned):
            return int(cleaned)

    return None


def regular(job):
    emp = job.get('emp', [])

    if isinstance(emp, str):
        emp = [emp]

    return isinstance(emp, list) and any(
        '정규직' in str(x) or '무기계약' in str(x)
        for x in emp
    )


def candidates(posts, history, today):
    blocked = {
        str(x) for x in history.get('posted_ids', [])
    }

    blocked.update(
        str(x.get('job_id'))
        for x in history.get('records', [])
        if x.get('job_id')
    )

    seen = set()
    found = []

    for job in posts:
        if not validate_candidate(job, today):
            continue

        jid = str(job.get('id', '')).strip()
        due = parse_date(job.get('due'))

        if not jid or not due or jid in blocked or jid in seen:
            continue

        days = (due - today).days

        if not MIN_DAYS <= days <= MAX_DAYS:
            continue

        if not job.get('title') or not job.get('org'):
            continue

        url = str(job.get('url', '')).strip()
        parsed = urllib.parse.urlparse(url)

        if (
            parsed.scheme != 'https'
            or parsed.hostname not in (
                'job.alio.go.kr',
                'kllollain-max.github.io'
            )
        ):
            continue

        seen.add(jid)

        count = parse_count(
            job.get('verified_hiring_count')
        )

        if count is None:
            count = parse_count(job.get('n'))

        if count is None:
            priority = 0
        elif count >= 100:
            priority = 4
        elif count >= 50:
            priority = 3
        elif count >= 30:
            priority = 2
        else:
            priority = 1

        found.append({
            'id': jid,
            'org': str(job['org']),
            'title': str(job['title']),
            'url': url,
            'due': str(due),
            'days': days,
            'regular': regular(job),
            'count': count,
            'employment': ' · '.join(map(str, job.get('emp', []))) if isinstance(job.get('emp'), list) else str(job.get('emp') or '공고 확인'),
            'location': str(job.get('location') or job.get('region') or '공고 확인'),
            'start': str(job.get('start') or job.get('start_date') or ''),
            'priority': priority
        })

    found.sort(
        key=lambda j: (
            -int(j['regular']),
            -j['priority'],
            -(j['count'] if j['count'] is not None else -1),
            j['days'],
            j['id']
        )
    )

    return found


def validate_candidate(job, today):
    """Return true only for currently eligible ALIO posts."""
    if not isinstance(job, dict):
        return False
    due = parse_date(job.get('due'))
    if due is None or not MIN_DAYS <= (due - today).days <= MAX_DAYS:
        return False
    if not str(job.get('id') or '').strip() or not job.get('title') or not job.get('org'):
        return False
    # Exclude explicit cancellation or withdrawal notices in source titles.
    # This does not establish the current status of notices without such markers.
    if re.search(r'취\s*소|철\s*회', str(job['title'])):
        return False
    try:
        parsed = urllib.parse.urlparse(str(job.get('url') or '').strip())
    except ValueError:
        return False
    return parsed.scheme == 'https' and parsed.hostname in ('job.alio.go.kr', 'kllollain-max.github.io')


def compose(job):
    """Show verified recruitment highlights in the main post."""
    org = re.sub(r'\s+', ' ', str(job['org'])).strip()
    count = job.get('count')
    employment = str(job.get('employment') or '').strip()
    hiring = (employment + ' ' if employment != '공고 확인' else '') + (str(count) + '명 모집' if count is not None else '채용')
    due = parse_date(job.get('due'))
    deadline = str(due.month) + '월 ' + str(due.day) + '일 마감' if due else '마감일 공고 확인'
    result = '📢 공공기관 채용정보\n\n🏢 ' + org + '\n\n👥 ' + hiring + '\n\n📅 ' + deadline + '\n\n💬 지원자격·접수정보는 답글 확인'
    if len(result) > 500:
        raise ValueError('Threads post exceeds 500 characters')
    if os.getenv('THREADS_CONVERSATION_ENABLED', 'false').lower() == 'true':
        return conversation_main(job)
    return enrich_main(result, job) if os.getenv('THREADS_EDITORIAL_ENABLED', 'false').lower() == 'true' else result


def api(method, path, token, params=None):
    if method.upper() != "GET":
        raise RuntimeError("Recovery mode: live SNS writes are disabled pending separate approval")
    if os.getenv('THREADS_NO_SEND', 'false').lower() == 'true':
        raise RuntimeError('Threads API disabled in test mode')
    url = API + path

    payload = None

    if params:
        url += '?' + urllib.parse.urlencode(params)

    if method == 'POST':
        payload = b''

    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            'Authorization': 'Bearer ' + token,
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    )

    # Timings exclude credentials, URLs and content. No request retries here.
    print('Threads API request start:', datetime.now(KST).isoformat(), method, flush=True)
    try:
        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:
            result = json.load(response)
            print('Threads API response received:', datetime.now(KST).isoformat(), method, flush=True)
            return result

    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode(
            'utf-8',
            errors='replace'
        )

        print('')
        print('=== Threads API Error ===')
        print('HTTP status:', exc.code)
        print('Endpoint:', method, path)

        try:
            error_data = json.loads(raw_body)
            error = error_data.get('error', {})

            print('Error code:', error.get('code'))
            print(
                'Error subcode:',
                error.get('error_subcode')
            )
            print(
                'Error type:',
                error.get('type')
            )
            print(
                'Error message:',
                error.get('message')
            )
        except (ValueError, TypeError, AttributeError):
            print('Error response could not be parsed')

        print('=========================')

        raise RuntimeError(
            f'Threads API request failed: HTTP {exc.code}'
        ) from None

    except urllib.error.URLError as exc:
        print('Threads API network request failed')
        raise RuntimeError(
            'Threads API network error'
        ) from None


def verify_account(token, expected_id=None):
    """Use the authenticated Threads ID; strictly verify the account username."""
    print('')
    print('=== Threads Account Verification ===')

    account = api(
        'GET',
        '/me',
        token,
        {'fields': 'id,username'}
    )
    actual_id = str(account.get('id', '')).strip()
    username = str(account.get('username', '')).strip().lstrip('@')

    if not actual_id.isdigit():
        raise RuntimeError('Threads API returned an invalid user ID')

    # Never rely on a manually typed ID to identify the account.
    # Prevent publishing to another account if the token is replaced.
    expected_username = os.environ.get(
        'THREADS_EXPECTED_USERNAME', 'hid_119'
    ).strip().lstrip('@')
    if not expected_username:
        raise RuntimeError('Missing expected Threads username')
    if username.casefold() != expected_username.casefold():
        raise RuntimeError(
            'Token belongs to a different Threads account: '
            + username
        )

    print('API username:', username)
    print('Account ID obtained directly from Threads API')
    print('Account verification successful')
    return actual_id



def compose_reply(job):
    """Verified recruitment details with an intact profile CTA."""
    count = str(job['count']) + '명' if job.get('count') is not None else '공고 확인'
    start = str(job.get('start') or '').strip()
    period = (start + ' ~ ' if start else '마감 ') + str(job['due'])
    lines = [
        '🏢 기관명: ' + str(job['org']),
        '📌 고용형태: ' + str(job.get('employment') or '공고 확인'),
        '👥 채용인원: ' + count,
        '📍 근무지: ' + str(job.get('location') or '공고 확인'),
        '📅 접수기간: ' + period,
    ]
    qualification = str(job.get('qualification') or '').strip()
    if qualification:
        lines.append('📋 지원자격: ' + ' '.join(qualification.split()))
    cta = '🔗 상세 자격·접수방법 확인 → 프로필 링크의 커리어픽'
    result = '\n\n'.join(lines + [cta])
    if len(result) > 500 and qualification:
        lines.pop()
        result = '\n\n'.join(lines + [cta])
    if len(result) > 500:
        raise ValueError('Threads reply exceeds 500 characters')
    return result


def create_media(token, params):
    if os.getenv('THREADS_NO_SEND', 'false').lower() == 'true':
        raise RuntimeError('Threads API publishing disabled in test mode')
    container = api('POST', '/me/threads', token, params)
    creation_id = container.get('id')
    if not creation_id:
        raise RuntimeError('Threads container ID missing')

    # Both image and text/reply containers may require asynchronous processing.
    # Never submit a container to threads_publish before Meta reports FINISHED.
    if params.get('media_type') in ('IMAGE', 'TEXT'):
        for attempt in range(24):
            status = api('GET', '/' + str(creation_id), token,
                         {'fields': 'status,error_message'})
            state = str(status.get('status', '')).upper()
            print('Threads media processing:', state, f'({attempt + 1}/24)')
            if state == 'FINISHED':
                # Meta's publish endpoint can lag the FINISHED status.
                time.sleep(10)
                break
            if state in ('ERROR', 'EXPIRED'):
                raise RuntimeError(
                    'Threads media processing failed: '
                    + str(status.get('error_message') or state)
                )
            time.sleep(5)
        else:
            raise RuntimeError(
                'Threads media processing timed out; do not publish prematurely'
            )

    print('Threads media container created; attempting final publish')
    try:
        published = api('POST', '/me/threads_publish', token,
                        {'creation_id': creation_id})
    except RuntimeError:
        # An API failure is not proof that the remote publish did not happen.
        # Preserve the pending reservation for manual reconciliation.
        print('Final Threads publish not confirmed; keep reservation pending')
        raise
    post_id = published.get('id')
    if not post_id:
        raise RuntimeError('Threads publish ID missing')
    return str(post_id)


def image_ready(url):
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.status == 200 and response.headers.get('Content-Type', '').startswith('image/')
    except (urllib.error.URLError, TimeoutError):
        return False


def check_history_before_send(record, history):
    """Fail closed if the reloaded history conflicts with this reservation.

    This check cannot coordinate with a legacy publisher that ignores remote
    claims. A separately verified, quiescent cutover remains mandatory.
    """
    slot = datetime.fromisoformat(record['scheduled_at'])
    if slot.tzinfo is None:
        raise RuntimeError('Reservation slot has no timezone')
    day = slot.astimezone(KST).date().isoformat()
    records = history.get('records', [])
    if sum(item is record for item in records) != 1:
        raise RuntimeError('Reservation missing or duplicated in history')
    for item in records:
        if item is record:
            continue
        other_slot = item.get('scheduled_at')
        if not other_slot:
            if not item.get('reserved_date') or item.get('reserved_date') == day:
                raise RuntimeError('Legacy same-day slot unknown; reconcile before sending')
            continue
        try:
            other = datetime.fromisoformat(other_slot)
            if other.tzinfo is None:
                raise ValueError('naive slot')
        except (ValueError, TypeError):
            raise RuntimeError('Invalid historical slot; reconcile before sending') from None
        if other == slot:
            raise RuntimeError('Slot already present in history; do not send')


def restore_accepted_receipt(record, history, remote):
    """Restore a confirmed main-post receipt; never call a Threads endpoint.

    The caller must persist the returned history through the normal conflict
    checked history mechanism. This does not recover or resend any replies.
    """
    if sum(item is record for item in history.get('records', [])) != 1:
        raise RuntimeError('Reservation missing or duplicated in history')
    slot = record.get('scheduled_at')
    run_id = str(record.get('run_id', ''))
    if not slot or not run_id.isdigit():
        raise RuntimeError('Unverified reservation identity')
    remote_record = remote.read(slot)
    if not isinstance(remote_record, dict) or remote_record.get('state') != 'accepted':
        raise RuntimeError('Remote receipt is not accepted; manual review')
    try:
        local_slot = datetime.fromisoformat(slot)
        remote_slot = datetime.fromisoformat(remote_record.get('slot', ''))
        if local_slot.tzinfo is None or remote_slot.tzinfo is None or local_slot != remote_slot:
            raise ValueError('slot mismatch')
    except (ValueError, TypeError):
        raise RuntimeError('Remote receipt slot mismatch') from None
    post_id = remote_record.get('post_id')
    if str(remote_record.get('run_id', '')) != run_id or not isinstance(post_id, str) or not post_id.isdigit():
        raise RuntimeError('Remote receipt identity mismatch')
    previous_id = record.get('threads_post_id')
    if previous_id and previous_id != post_id:
        raise RuntimeError('Conflicting post ID; manual review')
    for other in history['records']:
        if other is not record and other.get('threads_post_id') == post_id:
            raise RuntimeError('Post ID belongs to another reservation')
    if record.get('status') not in ('pending', 'published'):
        raise RuntimeError('Unsupported local reservation status')
    record['threads_post_id'] = post_id
    record['status'] = 'published'
    record['request_status'] = 'confirmed'
    if record.get('job_id') and record['job_id'] not in history['posted_ids']:
        history['posted_ids'].append(record['job_id'])
    return post_id


def publish_post(record, history):
    if os.getenv(
        'THREADS_ENABLED', 'false'
    ).lower() != 'true':
        print(
            'Publishing disabled. '
            'Pending reservation requires manual reconciliation.'
        )
        return

    token = os.environ.get(
        'THREADS_ACCESS_TOKEN', ''
    )

    user_id = os.environ.get(
        'THREADS_USER_ID', ''
    ).strip()

    if not token:
        raise RuntimeError('Missing THREADS_ACCESS_TOKEN')

    # Verify username and use the ID returned by the token's account.
    user_id = verify_account(token, user_id)

    print('')
    print('=== Threads Publishing ===')
    if not record.get('threads_post_id'):
        check_history_before_send(record, history)
        if record.get('request_status') == 'attempted':
            raise RuntimeError('Ambiguous request; reconcile before retry')
        image_url = record.get('image_url', '')
        force_text = os.getenv('THREADS_IMAGE_PREPARATION_FAILED', 'false').lower() == 'true'
        if image_url and not force_text and image_ready(image_url):
            print('Publishing image post')
            params = {'media_type': 'IMAGE', 'image_url': image_url, 'text': record['text']}
        elif image_url:
            # This decision is made before any publishing request or slot claim.
            # Preserve the intended image for review, but record the actual format.
            text = record.get('text')
            if not isinstance(text, str) or not text.strip() or len(text) > 500:
                raise RuntimeError('Image unavailable and text is invalid')
            record['requested_image_url'] = image_url
            record['image_url'] = ''
            record['image_fallback'] = 'pre_request_unavailable'
            print('Public image unavailable; using validated text before sending')
            params = {'media_type': 'TEXT', 'text': text}
        else:
            params = {'media_type': 'TEXT', 'text': record['text']}
        from scripts.threads_remote_claim import GitHubClaims
        remote = GitHubClaims(os.environ.get('THREADS_CLAIM_REPO', ''),
                              os.environ.get('THREADS_CLAIM_BRANCH', ''),
                              os.environ.get('THREADS_CLAIM_TOKEN', ''))
        claim_sha = remote.begin(record['scheduled_at'], record['run_id'])
        record['request_status'] = 'attempted'
        save(history)
        post_id = create_media(token, params)
        # Preserve the receipt in runner logs before the conditional remote write.
        # The sending claim remains a manual-review hold if recording fails.
        print('Threads API returned post ID; reconcile if receipt write fails:', post_id, flush=True)
        # If this fails, the remote sending claim remains a permanent hold.
        remote.accept(record['scheduled_at'], record['run_id'], claim_sha, post_id)
        record['status'] = 'published'
        record['threads_post_id'] = post_id
        record['published_at'] = datetime.now(KST).isoformat()
        if record.get('job_id') and record['job_id'] not in history['posted_ids']:
            history['posted_ids'].append(record['job_id'])
        save(history)
        print('Published Threads post ID:', post_id)

    if record.get('content_type') in ('discussion', 'tip') and not record.get('reply_text') and not record.get('engagement_text'):
        return

    if record.get('reply_post_id') and (not record.get('engagement_text') or record.get('engagement_post_id') or record.get('engagement_status') == 'needs_review'):
        return
    # Threads may not accept a reply immediately after the parent image post.
    # Check that the parent is readable and allow propagation before creating
    # the reply. Never retry an ambiguous publish automatically.
    try:
        parent = api('GET', '/' + str(record['threads_post_id']), token,
                     {'fields': 'id'})
        if str(parent.get('id', '')) != str(record['threads_post_id']):
            raise RuntimeError('Parent post not yet confirmed by Threads API')
        if record.get('published_at'):
            print('Waiting 20 seconds before first reply to new parent post')
            time.sleep(20)
        if not record.get('reply_post_id'):
            reply_id = create_media(token, {
                'media_type': 'TEXT',
                'text': record.get('reply_text', '🔗 자세한 채용공고: 커리어픽 프로필링크'),
                'reply_to_id': record['threads_post_id']
            })
            record['reply_post_id'] = reply_id
            record['reply_published_at'] = datetime.now(KST).isoformat()
            save(history)
            print('Published reply ID:', reply_id)
        if record.get('engagement_text') and not record.get('engagement_post_id') and record.get('engagement_status') != 'needs_review':
            if not validated_reply(record['engagement_text']):
                raise RuntimeError('Invalid engagement reply')
            # Allow the parent and first reply to propagate before the next API call.
            time.sleep(10)
            # A second reply is attached to the original post, not to reply one.
            engagement_id = create_media(token, {
                'media_type': 'TEXT',
                'text': record['engagement_text'],
                'reply_to_id': record['threads_post_id']
            })
            record['engagement_post_id'] = engagement_id
            record['engagement_published_at'] = datetime.now(KST).isoformat()
            save(history)
            print('Published engagement reply ID:', engagement_id)
    except RuntimeError as exc:
        print('Reply publish failed; original post remains recorded:', str(exc))
        # Keep post ID for manual reconciliation; never publish the original again.
        if record.get('reply_post_id'):
            record['engagement_status'] = 'needs_review'
        else:
            record['reply_status'] = 'needs_review'
        record['reply_failure_reason'] = str(exc)[:300]
        record['reply_failed_at'] = datetime.now(KST).isoformat()
        save(history)


def main():
    if len(sys.argv)>1 and sys.argv[1] not in ("preview",):
        raise RuntimeError("Recovery mode: only local preview is available; reconcile private history before publishing")
    command = (
        sys.argv[1]
        if len(sys.argv) > 1
        else 'preview'
    )

    if command not in (
        'prepare',
        'publish',
        'preview',
        'diagnose',
        'recover-accepted'
    ):
        raise ValueError(
            'Use prepare, publish, preview, diagnose or recover-accepted'
        )

    today = datetime.now(
        KST
    ).date().isoformat()

    history = load(
        HISTORY,
        {
            'posted_ids': [],
            'records': []
        }
    )

    history.setdefault('posted_ids', [])
    history.setdefault('records', [])

    if command == 'recover-accepted':
        # Explicit, local-only recovery; no automatic retries or Threads calls.
        run_id = os.environ.get('THREADS_RECOVER_RUN_ID', '')
        if not run_id.isdigit():
            raise RuntimeError('Explicit original run ID required')
        matches = [r for r in history['records'] if str(r.get('run_id', '')) == run_id]
        if len(matches) != 1:
            raise RuntimeError('No unique reservation for original run')
        from scripts.threads_remote_claim import GitHubClaims
        remote = GitHubClaims(os.environ.get('THREADS_CLAIM_REPO', ''),
                              os.environ.get('THREADS_CLAIM_BRANCH', ''),
                              os.environ.get('THREADS_CLAIM_TOKEN', ''))
        post_id = restore_accepted_receipt(matches[0], history, remote)
        import tempfile
        tmp_name = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=HISTORY.parent,
                                             prefix='.threads-recovery-', delete=False) as temp:
                tmp_name = temp.name
                json.dump(history, temp, ensure_ascii=False, indent=2)
                temp.write('\n')
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(tmp_name, HISTORY)
        finally:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
        print('Recovered confirmed main post ID locally:', post_id,
              '; persist history separately after conflict review')
        return

    if command == 'diagnose':
        # Read-only diagnostic: no publishing and no history mutation.
        pending_records = [
            r for r in history['records'] if r.get('status') == 'pending'
        ]
        for record in pending_records:
            print(
                'Unresolved reservation:',
                'job_id=' + str(record.get('job_id', '')),
                'run_id=' + str(record.get('run_id', '')),
                'created_at=' + str(record.get('created_at', '')),
                'has_post_id=' + str(bool(record.get('threads_post_id')))
            )

        token = os.environ.get('THREADS_ACCESS_TOKEN', '')
        configured_id = os.environ.get('THREADS_USER_ID', '')
        if not token:
            raise RuntimeError('Missing THREADS_ACCESS_TOKEN')
        actual_id = verify_account(token, configured_id)
        # Scan a bounded number of remote pages without mutating history.
        # A missing match is inconclusive, even if every page was scanned.
        if pending_records:
            try:
                remote_posts = []
                after = None
                more_pages = False
                for page in range(10):
                    params = {'fields': 'id,text,timestamp', 'limit': 100}
                    if after:
                        params['after'] = after
                    remote = api('GET', '/me/threads', token, params)
                    remote_posts.extend(remote.get('data', []))
                    paging = remote.get('paging') or {}
                    cursors = paging.get('cursors') or {}
                    next_after = cursors.get('after')
                    more_pages = bool(paging.get('next'))
                    if not more_pages or not next_after or next_after == after:
                        break
                    after = next_after
                print('Remote reconciliation scanned posts:', len(remote_posts))
                for record in pending_records:
                    matches = [
                        str(post.get('id', ''))
                        for post in remote_posts
                        if post.get('text') == record.get('text')
                        and str(post.get('id', '')).isdigit()
                    ]
                    print('Remote match for job', record.get('job_id'),
                          'count:', len(matches))
                    if len(matches) == 1:
                        print('Confirmed remote post ID:', matches[0])
                    elif len(matches) > 1:
                        print('Multiple remote matches; manual review required')
                    else:
                        print('No exact match in scanned posts; not proof of absence')
                if more_pages:
                    print('Additional remote pages may exist; reconciliation incomplete')
            except (RuntimeError, ValueError, TypeError) as exc:
                print('Remote reconciliation unavailable:', type(exc).__name__)
        print('Publishing enabled:', os.getenv('THREADS_ENABLED', 'false'))
        # Report legacy posts without recorded replies; do not auto-reply.
        missing_replies = [
            r for r in history['records']
            if r.get('status') == 'published'
            and r.get('threads_post_id')
            and not r.get('reply_post_id')
        ]
        print('Published posts missing recorded reply:', len(missing_replies))
        for record in missing_replies:
            print('Missing reply for job:', record.get('job_id'),
                  'has_reply_text:', bool(record.get('reply_text')),
                  'reply_status:', record.get('reply_status', 'unknown'))
        print('Pending reservations:', sum(
            r.get('status') == 'pending' for r in history['records']
        ))
        # Make the scheduled diagnostic result actionable in GitHub's run summary.
        if os.getenv('GITHUB_STEP_SUMMARY'):
            summary_path = Path(os.environ['GITHUB_STEP_SUMMARY'])
            published_count = sum(r.get('status') == 'published' for r in history['records'])
            pending_count = len(pending_records)
            with summary_path.open('a', encoding='utf-8') as summary:
                summary.write('## CareerPick Threads diagnostic\\n\\n'.replace('\\n', '\n'))
                summary.write(f'- Pending reservations: **{pending_count}**\\n'.replace('\\n', '\n'))
                summary.write(f'- Published records: **{published_count}**\\n'.replace('\\n', '\n'))
                summary.write(f'- Published posts without recorded reply: **{len(missing_replies)}**\\n'.replace('\\n', '\n'))
                if pending_count:
                    summary.write('- **Action needed:** inspect remote match results in the job log before reconciling.\\n'.replace('\\n', '\n'))
                if missing_replies:
                    summary.write('- **Review:** legacy missing replies are not automatically reposted.\\n'.replace('\\n', '\n'))
        print('Published records:', sum(
            r.get('status') == 'published' for r in history['records']
        ))
        print('Account ID:', actual_id)
        try:
            limits = api('GET', '/me/threads_publishing_limit', token,
                         {'fields': 'quota_usage,config'})
            print('Publishing limit response:', json.dumps(limits, ensure_ascii=False))
        except RuntimeError as exc:
            print('Publishing limit check failed:', str(exc))
        print('Diagnostic only: no post was created, no history changed.')
        return

    if command == 'publish':
        run_id = os.getenv(
            'GITHUB_RUN_ID', ''
        )

        if not run_id:
            raise RuntimeError(
                'GITHUB_RUN_ID is required for publishing'
            )

        pending = [
            record
            for record in history['records']
            if (
                record.get('status') in ('pending', 'published')
                and record.get('run_id') == run_id
                and (not record.get('reply_post_id') or (record.get('engagement_text') and not record.get('engagement_post_id') and record.get('engagement_status') != 'needs_review'))
            )
        ]

        if len(pending) != 1:
            print(
                'No unique pending post for this run. '
                'Nothing to publish.'
            )
            return

        publish_post(
            pending[0],
            history
        )

        return

    # Stage 1: new material only for the scheduled midday and afternoon slots.
    # Existing job path remains in use for the morning and evening slots.
    stage1 = command == 'prepare' and os.getenv('THREADS_NEW_CONTENT', 'false').lower() == 'true'
    stage1_cron = os.getenv('THREADS_SCHEDULE_CRON', '')
    if stage1 and stage1_cron not in ('0 23 * * *', '0 3 * * *', '0 7 * * *', '0 11 * * *'):
        raise RuntimeError('Scheduled slot required for staged content')
    if stage1 and stage1_cron in ('0 3 * * *', '0 7 * * *'):
        from scripts.threads_transition_preview import slot_from_cron
        from scripts.threads_content_preview import generate
        from scripts.threads_post_model import build_work, assert_safe_to_reserve
        from datetime import timedelta
        if os.getenv('THREADS_ENABLED', 'false').lower() != 'true':
            return
        if os.getenv('GITHUB_RUN_ATTEMPT', '1') != '1':
            raise RuntimeError('Reruns require manual reconciliation')
        cron = os.getenv('THREADS_SCHEDULE_CRON', '')
        hour = slot_from_cron(cron)
        now = datetime.now(KST)
        scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        print('Scheduled slot:', scheduled.isoformat(), 'preparation:', now.isoformat(), flush=True)
        if now < scheduled or now >= scheduled + timedelta(hours=2):
            raise RuntimeError('Scheduled slot is not current; manual review')
        run_id = os.getenv('GITHUB_RUN_ID', '')
        if not run_id:
            raise RuntimeError('GITHUB_RUN_ID is required')
        if sum(r.get('reserved_date') == today and r.get('status') in ('pending', 'published') for r in history['records']) >= MAX_DAILY:
            raise RuntimeError('Daily limit reached')
        draft = generate(hour, [], now.date(), now.date().isoformat())
        work = build_work('discussion' if hour == 12 else 'tip', scheduled, draft['body'])
        if any(r.get('reserved_date') == today and r.get('status') in ('pending', 'published') and not r.get('scheduled_at') for r in history['records']):
            raise RuntimeError('Legacy reservation lacks slot; reconcile before proceeding')
        assert_safe_to_reserve(work, history)
        history['records'].append({'task_id': work.task_id, 'content_hash': work.content_hash,
            'content_type': work.kind, 'job_ids': [], 'reserved_date': today,
            'status': 'pending', 'run_id': run_id, 'created_at': now.isoformat(), 'scheduled_at': scheduled.isoformat(),
            'text': work.body, 'reply_text': '', 'engagement_text': '', 'image_url': '', 'image_job': None})
        save(history)
        print('Reserved non-job content:', work.task_id)
        return

    posts = load(
        DATA,
        {'posts': []}
    ).get('posts', [])

    if not isinstance(posts, list):
        raise ValueError(
            'alio.json posts must be a list'
        )

    chosen = candidates(
        posts,
        history,
        date.fromisoformat(today)
    )

    print(
        f'Source: {len(posts)}; '
        f'eligible: {len(chosen)}'
    )

    if command == 'preview':
        for job in chosen[:5]:
            print('')
            print(compose(job))

        print('')
        print(
            'Preview only; nothing published.'
        )
        return

    if os.getenv(
        'THREADS_ENABLED', 'false'
    ).lower() != 'true':
        print(
            'Publishing disabled; no reservation made.'
        )
        return

    daily = sum(
        record.get('reserved_date') == today
        and record.get('status') in (
            'pending',
            'published'
        )
        for record in history['records']
    )

    has_waiting = any(r.get('status') == 'pending' and not r.get('threads_post_id') for r in history['records'])
    if (daily >= MAX_DAILY and not has_waiting) or (not chosen and not has_waiting):
        print(
            f'No reservation. '
            f'Daily reserved: {daily}/{MAX_DAILY}; '
            f'eligible: {len(chosen)}'
        )
        return

    run_id = os.getenv(
        'GITHUB_RUN_ID', ''
    )

    if not run_id:
        raise RuntimeError(
            'GITHUB_RUN_ID is required for reservation'
        )

    # Any ambiguous reservation may already be published; never reserve another.
    waiting = [
        r for r in history['records']
        if r.get('status') == 'pending' and not r.get('threads_post_id')
    ]
    if waiting:
        waiting.sort(key=lambda r: r.get('created_at', ''))
        print(
            'Unresolved pending Threads reservation:',
            waiting[0].get('job_id'),
            '- manual reconciliation required before another publish attempt.'
        )
        print('No new reservation created; avoiding possible duplicate post.')
        return

    from scripts.threads_transition_preview import slot_from_cron
    from datetime import timedelta
    hour = slot_from_cron(os.getenv('THREADS_SCHEDULE_CRON', ''))
    now = datetime.now(KST)
    scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    print('Scheduled slot:', scheduled.isoformat(), 'preparation:', now.isoformat(), flush=True)
    if not scheduled <= now < scheduled + timedelta(hours=2):
        raise RuntimeError('Scheduled slot is not current')
    if any(r.get('reserved_date') == today and r.get('status') in ('pending', 'published') and not r.get('scheduled_at') for r in history['records']):
        raise RuntimeError('Legacy reservation lacks slot; reconcile before proceeding')
    claim_slot = scheduled.isoformat()
    if any(r.get('scheduled_at') == claim_slot for r in history['records']):
        raise RuntimeError('Slot already reserved')

    job = chosen[0]

    # Alternate from the last confirmed published format across date boundaries.
    prior = next((r for r in reversed(history['records'])
                  if r.get('status') == 'published' and r.get('threads_post_id')
                  and 'image_url' in r), None)
    text_first = prior is None or bool(prior.get('image_url'))
    history['records'].append({
        'job_id': job['id'],
        'scheduled_at': claim_slot,
        'reserved_date': today,
        'status': 'pending',
        'run_id': run_id,
        'created_at': datetime.now(
            KST
        ).isoformat(),
        'text': compose(job),
        'reply_text': compose_reply(job),
        'engagement_text': engagement(job),
        'image_url': '' if text_first else 'https://kllollain-max.github.io/careerpick/threads-images/' + urllib.parse.quote(re.sub(r'[^A-Za-z0-9_-]', '_', job['id'])[:70] + '.jpg'),
        'image_job': None if text_first else job
    })

    save(history)

    print('Reserved job:', job['id'])
    print(compose(job))


if __name__ == '__main__':
    main()
