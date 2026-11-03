"""Offline-only Threads copy prototype. Never imports the publisher or posts.

Job facts are supplied by a caller after independent source verification. The
caller, not this module, must re-check cancellation and exact closing times.
"""
from datetime import date
from hashlib import sha256
from urllib.parse import urlsplit, parse_qs
import re

HOOKS = (
    "지원 전에 살펴볼 채용 소식이에요.",
    "직무와 마감일을 함께 확인해 보세요.",
    "관심 직무가 있다면 공고를 살펴보세요.",
    "이번 채용에서 확인할 내용을 모았어요.",
    "지원 조건을 비교하기 전, 먼저 볼 공고예요.",
    "채용 일정에 넣어둘 공고를 소개합니다.",
)
STRATEGY_HOOKS = (
    '이 공고는 지원 전 조건을 이렇게 살펴보세요.',
    '지원 여부를 정할 때 직무부터 확인해 보세요.',
    '채용 일정과 지원 조건을 함께 점검해 보세요.',
)
CONVERSATIONS = (
    "자기소개서를 쓰다 보면 경험을 고르는 일부터 막힐 때가 있어요.\n\n여러분은 어떤 기준으로 경험을 고르나요?",
    "면접 준비를 하다 보면 답변을 외울지, 핵심만 정리할지 고민되죠.\n\n어떤 방식이 더 잘 맞으셨나요?",
    "직무와 근무지 모두 중요해서 지원을 망설일 때가 있어요.\n\n공고를 볼 때 무엇부터 확인하시나요?",
)
TIPS = (
    "자기소개서 쓰기 전, 이 세 가지부터 정리해 보세요.\n\n1. 공고의 직무 내용에서 중요한 업무 표시하기\n2. 그 업무와 연결되는 경험 하나 고르기\n3. 당시 행동과 결과를 구체적으로 적기",
    "면접 준비는 공고를 다시 읽는 것부터 시작해 보세요.\n\n1. 주요 업무와 지원 자격에 밑줄 긋기\n2. 경험별로 본인이 한 일 정리하기\n3. 설명하기 어려운 부분을 소리 내어 연습하기",
    "NCS 준비 계획을 세울 때는 범위를 먼저 확인해 보세요.\n\n1. 채용 공고에서 평가 영역 확인하기\n2. 시간 제한을 두고 연습하기\n3. 틀린 문제의 이유를 기록하기",
)


def official_url(value):
    """Restrict preview to a real ALIO listing URL, without claiming reachability."""
    try:
        p = urlsplit(value)
        return (p.scheme == 'https' and p.hostname == 'job.alio.go.kr'
                and p.port in (None, 443) and not p.username and not p.password
                and p.path in ('/recruitview.do', '/mobile2021/recruit/recruitView.do') and bool(re.search(r'(?:^|&)idx=\d+(?:&|$)', p.query))
                and not p.fragment)
    except (TypeError, ValueError):
        return False


def checked_job(job, today):
    # Verification must be explicitly supplied; an ALIO URL is not evidence.
    if not isinstance(job, dict) or job.get('verified') is not True:
        raise ValueError('independent verification required')
    for key in ('org', 'title', 'due', 'url'):
        if not isinstance(job.get(key), str) or not job[key].strip():
            raise ValueError('missing job field: ' + key)
    if any(x in job['title'] for x in ('취소', '철회', '마감')):
        raise ValueError('cancelled or closed title')
    if not official_url(job['url']):
        raise ValueError('invalid official URL')
    try:
        due = date.fromisoformat(job['due'])
    except ValueError as exc:
        raise ValueError('invalid date') from exc
    # Date-only same-day deadline cannot safely establish remaining time.
    if due <= today:
        raise ValueError('closed or exact deadline unknown')
    count = job.get('count')
    if count is not None and (type(count) is not int or count < 1):
        raise ValueError('invalid count')
    return job


def choose(options, seed, previous_hooks=()):
    start = int.from_bytes(sha256(str(seed).encode()).digest()[:4], 'big') % len(options)
    for i in range(len(options)):
        candidate = options[(start + i) % len(options)]
        if candidate.split('\n', 1)[0] not in previous_hooks:
            return candidate
    raise ValueError('all hooks recently used')


def generate(hour, jobs, today, seed, previous_hooks=()):
    """Return a preview, not a scheduled post. Input verification is external."""
    if hour not in (8, 12, 16, 20):
        raise ValueError('unknown slot')
    if hour in (12, 16):
        body = choose(CONVERSATIONS if hour == 12 else TIPS, seed, previous_hooks)
        return {'slot': hour, 'type': 'conversation' if hour == 12 else 'tips', 'body': body, 'replies': [], 'topic': '취업준비'}
    valid = []
    seen = set()
    for job in jobs:
        try:
            j = checked_job(job, today)
        except ValueError:
            continue
        key = parse_qs(urlsplit(j['url']).query)['idx'][0]
        if key in seen:
            continue
        seen.add(key)
        valid.append(j)
    if not valid:
        raise ValueError('no independently verified eligible job')
    valid.sort(key=lambda j: (not bool(j.get('regular')), -(j.get('count') or 0), j['due']))
    j = valid[0]
    hook = choose(HOOKS if hour == 8 else STRATEGY_HOOKS, seed, previous_hooks)
    count = f"{j['count']}명" if j.get('count') is not None else '인원 원문 확인'
    body = (f"{hook}\n\n{j['org']} · {j['title']}\n모집 {count} · 마감 {j['due']}\n\n"
            "직무 내용과 지원 자격은 원문에서 확인해 주세요.\n" + j['url'])
    if hour == 20:
        body += "\n\n지원할 때 직무와 근무지 중 무엇을 먼저 보시나요?"
    if len(body) > 500:
        raise ValueError('post exceeds 500 characters')
    return {'slot': hour, 'type': 'job' if hour == 8 else 'strategy', 'body': body, 'replies': [], 'topic': '채용정보'}
