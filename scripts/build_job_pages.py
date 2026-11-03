
"""Generate searchable static ALIO job pages for CareerPick.

Run from the repository root: python scripts/build_job_pages.py
"""

import ipaddress
import json
import re
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'alio.json'
DETAIL = ROOT / 'alio-detail.json'
OUT = ROOT / 'jobs'
BASE = 'https://kllollain-max.github.io'

DETAIL_LABELS = {
    'recrutSeNm': '채용 구분',
    'aplyQlfcCn': '지원 자격',
    'disqlfcRsn': '결격사유',
    'scrnprcdrMthdExpln': '전형 절차',
    'prefCn': '우대사항',
    'prefCondCn': '우대조건',
}


def clean(value):
    if isinstance(value, list):
        return ', '.join(map(str, value))
    return str(value or '').strip()


def safe_url(value):
    value = clean(value)
    try:
        parsed = urlparse(value)
    except ValueError:
        return ''
    # URL은 공식 링크 후보만 허용합니다. 자격증명·비표준 포트·내부 주소는 배제합니다.
    try:
        host = (parsed.hostname or '').lower().rstrip('.')
        port = parsed.port
    except ValueError:
        return ''
    if parsed.scheme != 'https' or not host or parsed.username or parsed.password or port not in (None, 443):
        return ''
    if host in ('localhost', '0.0.0.0') or host.endswith(('.local', '.internal', '.localhost')):
        return ''
    try:
        # 사설·루프백·예약된 IP로 유도하는 공고 링크는 제공하지 않습니다.
        if not ipaddress.ip_address(host).is_global:
            return ''
    except ValueError:
        pass  # 정상적인 도메인 이름
    return value


def parse_date(value, end_of_day=False):
    """Accept valid ISO dates/times and common ALIO formats.

    For a date-only deadline, use the end of that date
    in Korea time.
    """
    raw = clean(value)
    if not raw:
        return ''

    raw = raw.replace('년', '-').replace('월', '-').replace('일', ' ').strip()
    raw = re.sub(r'(?<=\d)[./](?=\d)', '-', raw)
    raw = re.sub(r'\s+', ' ', raw)

    if re.fullmatch(r'\d{8}', raw):
        raw = f'{raw[:4]}-{raw[4:6]}-{raw[6:8]}'

    if re.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}', raw):
        y, m, d = map(int, raw.split('-'))
        try:
            parsed = date(y, m, d)
        except ValueError:
            return ''
        return (
            f'{parsed.isoformat()}T23:59:59+09:00'
            if end_of_day
            else parsed.isoformat()
        )

    normalized = (
        raw.replace(' ', 'T', 1)
        if 'T' not in raw and ' ' in raw
        else raw
    )

    if normalized.endswith('Z'):
        normalized = normalized[:-1] + '+00:00'

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return ''

    if parsed.tzinfo is None:
        return parsed.isoformat(timespec='seconds') + '+09:00'

    return parsed.isoformat(timespec='seconds')


def date_label(value, time_verified=True):
    """Show a clock time only when the source has verified it.

    ALIO date-only feeds are currently stored with a synthetic 23:59
    timestamp for internal sorting; that timestamp must not be displayed
    as an official application cutoff.
    """
    parsed = parse_date(value)
    if not parsed:
        return clean(value) or '공식 공고 확인'
    if 'T' not in parsed or time_verified is False:
        return parsed[:10]
    return parsed[:16].replace('T', ' ')


def is_closed(due):
    parsed = parse_date(due, end_of_day=True)
    if not parsed:
        return False

    try:
        deadline = datetime.fromisoformat(parsed)
        if deadline.tzinfo is None:
            return False
        return (
            deadline.astimezone(timezone.utc)
            < datetime.now(timezone.utc)
        )
    except ValueError:
        return False


def render(post, detail, related_posts=()):
    # The list feed can contain only the first work region. Use the same
    # notice's explicit detail regions throughout the rendered page, without
    # changing the collected post or inventing nationwide coverage.
    pid = clean(post.get('id'))
    detail_id = clean(detail.get('recrutPblntSn'))
    if (post.get('alio') and re.fullmatch(r'a[0-9]+', pid)
            and detail_id and detail_id != pid[1:]):
        # Explicitly mismatched detail belongs to another notice; do not mix
        # its qualification or process into this page either.
        detail = {}
    detail_region = detail.get('workRgnNmLst')
    if (post.get('alio') and re.fullmatch(r'a[0-9]+', pid)
            and (not detail_id or detail_id == pid[1:])
            and isinstance(detail_region, str) and detail_region.strip()):
        post = dict(post, region=', '.join(
            part.strip() for part in re.split(r'[,|]', detail_region)
            if part.strip()
        ) or post.get('region', ''))
    title = clean(post.get('title'))
    org = clean(post.get('org'))
    pid = clean(post.get('id'))

    canonical = f'{BASE}/jobs/{quote(pid, safe="")}.html'
    due = clean(post.get('due'))
    due_display = date_label(due, post.get('dueHasTime') is not False)
    deadline = parse_date(due, end_of_day=True)
    closed = is_closed(due)

    official = (
        safe_url(post.get('src'))
        or safe_url(post.get('url'))
    )
    # 기관 원문이 일시적으로 열리지 않을 때 ALIO 원본을 대체 확인 경로로 제공합니다.
    alio_reference = safe_url(post.get('url'))
    if alio_reference == official:
        alio_reference = ''
    # 허용 가능한 HTTPS 링크라는 뜻이지, 링크 응답이나 접수 가능성을 실시간 검증한 것은 아닙니다.

    fields = [
        ('기관명', org),
        (
            '모집인원',
            clean(post.get('n')) + '명'
            if post.get('n')
            else '공고 확인'
        ),
        ('고용형태', clean(post.get('emp')) or '공고 확인'),
        ('학력조건', clean(post.get('edu')) or '공고 확인'),
        ('근무지역', clean(post.get('region')) or '공고 확인'),
        ('접수마감', due_display),
    ]

    rows = '\n'.join(
        f'<dt>{escape(k)}</dt><dd>{escape(v)}</dd>'
        for k, v in fields
    )

    # 표시하는 내용은 ALIO 원본 필드에 존재하는 사실만 사용합니다.
    detail = detail if isinstance(detail, dict) else {}
    qualification = clean(detail.get('aplyQlfcCn'))
    process = clean(detail.get('scrnprcdrMthdExpln'))
    check_items = [
        ('지원 자격', '공고에 기재된 지원 자격을 확인하세요.' if qualification else '상세 자격조건은 공식 채용공고에서 확인하세요.'),
        ('접수 마감', f'표시된 마감일은 {due_display}입니다. 실제 마감시각과 접수방법은 공식 공고를 확인하세요.' if due else '공식 채용공고에서 접수기간과 마감시각을 확인하세요.'),
        ('전형 절차', '아래 채용 절차 항목과 공식 공고의 최신 일정을 비교하세요.' if process else '서류·필기·면접 실시 여부와 일정은 공식 공고에서 확인하세요.'),
    ]
    # 공고별 실제 데이터로 확인 항목을 구성합니다. 확인되지 않은 조건은 추정하지 않습니다.
    if post.get('region'):
        check_items.append(('근무 지역', f'표시된 근무지역은 {clean(post.get("region"))}입니다. 실제 배치 장소와 전근 가능성은 공식 공고를 확인하세요.'))
    if post.get('emp'):
        check_items.append(('고용 형태', f'표시된 고용형태는 {clean(post.get("emp"))}입니다. 계약기간과 정규직 전환 여부는 공식 공고를 확인하세요.'))
    if post.get('edu'):
        check_items.append(('학력 조건', f'표시된 학력조건은 {clean(post.get("edu"))}입니다. 자격증·경력·우대사항은 별도로 확인하세요.'))
    if not (qualification or process):
        check_items.append(('상세 자료', '자격·전형 상세정보가 제공되지 않아 공식 공고문과 첨부파일 확인이 필요합니다.'))
    checks = ''.join(
        f'<li><strong>{escape(label)}</strong> — {escape(message)}</li>'
        for label, message in check_items
    )
    detail_status = (
        '<p class="source-note">ALIO에서 제공된 상세 자격·전형 정보를 아래에 표시합니다. '
        '최종 지원 조건은 반드시 공식 원문을 기준으로 확인하세요.</p>'
        if qualification or process
        else '<p class="source-note">이 공고는 상세 자격·전형 데이터가 제공되지 않았습니다. '
        '아래 공식 채용공고에서 첨부파일과 최신 안내를 확인하세요.</p>'
    )
    # 공고에 확인된 정보와 직무 특성에 맞는 가이드를 우선 안내합니다.
    guide_items = [
        ('/guides/application-checklist.html', '지원 전 7가지 확인사항'),
        ('/guides/qualification-preference-guide.html', '지원자격·우대조건 해석법'),
        ('/guides/after-application-checklist.html', '지원서 제출 후 확인사항'),
        ('/guides/recruitment-corrections-guide.html', '정정공고·마감 변경 대응법'),
    ]
    # 직무 분류나 기관 유형만으로 NCS 필기시험 실시를 추정하지 않습니다.
    context = ' '.join((title, clean(post.get('desc')), qualification, process))
    # 필기전형 및 같은 줄/인접 줄의 NCS 시험과목만 인정합니다.
    # 서류·면접 단계의 직업기초능력 평가를 필기시험으로 오인하지 않습니다.
    process_lines = [line.strip() for line in process.splitlines() if line.strip()]
    ncs_exam_confirmed = False
    for index, line in enumerate(process_lines):
        written_stage = bool(re.search(r'필기\s*(?:전형|시험|평가|검사)', line))
        # "NCS 직업기초능력 필기시험"처럼 과목이 먼저 나오는 경우
        inline_exam = bool(re.search(
            r'(?:NCS|직업\s*기초\s*능력)[^\n]{0,35}필기\s*(?:전형|시험|평가|검사)',
            line, re.I
        ))
        # 과목명 뒤에 '필기시험'이 나오는 한 줄 전형도 명시적 근거입니다.
        if inline_exam:
            ncs_exam_confirmed = True
            break
        if not (written_stage or inline_exam):
            continue
        nearby = ' '.join(process_lines[index:index + 3]) if written_stage else line
        if written_stage:
            nearby = re.split(r'(?:면접|서류)\s*(?:전형|심사|평가)', nearby, maxsplit=1)[0]
        if re.search(r'NCS|직업\s*기초\s*능력|직무공통능력검사', nearby, re.I):
            ncs_exam_confirmed = True
            break
    if ncs_exam_confirmed:
        guide_items.append(('/guides/ncs-study-plan.html', 'NCS 4주 학습 계획'))
    if any(word in context for word in ('자기소개서', '자소서', '서류전형', '입사지원서', '경험기술')):
        guide_items.append(('/guides/self-introduction-star.html', 'STAR 자기소개서 작성법'))
    guide_links = (
        '<nav class="guide-links" aria-label="관련 취업 준비 가이드">'
        + ''.join(
            f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'
            for url, label in guide_items
        )
        + '</nav>'
    )
    # 같은 기관의 다른 ALIO 공고만 연결하며 모집분야가 같다고 추정하지 않습니다.
    related_items = []
    for other in related_posts:
        other_id = clean(other.get('id'))
        if other_id == pid or not re.fullmatch(r'a[0-9]+', other_id):
            continue
        other_title = clean(other.get('title'))
        if not other_title:
            continue
        related_items.append(
            f'<li><a href="/jobs/{escape(other_id, quote=True)}.html">'
            f'{escape(other_title)}</a>'
            f' <span class="muted">· 마감 {escape(date_label(other.get("due")))}</span></li>'
        )
        if len(related_items) >= 4:
            break
    related_html = (
        '<section aria-label="같은 기관의 다른 채용공고">'
        '<h2>같은 기관의 다른 채용공고</h2>'
        '<p class="source-note">같은 기관에서 게시한 별도 공고입니다. 모집분야와 지원 조건은 각 공고에서 확인하세요.</p>'
        '<ul class="related-jobs">' + ''.join(related_items) + '</ul></section>'
        if related_items else ''
    )
    # 자료가 없는 공고에 사실처럼 보이는 직무 설명을 생성하지 않습니다.
    # ALIO desc는 alio.py에서 ncsCdNmLst로 생성된 직무 분류입니다.
    # 글자 수나 구분자에 관계없이 실제 담당업무 설명으로 판단하지 않습니다.
    has_substantive_desc = False
    if qualification and process:
        coverage_note = '지원 자격과 채용 절차 정보가 제공된 공고입니다.'
    elif qualification or process or has_substantive_desc:
        coverage_note = '일부 상세 정보가 제공된 공고입니다. 누락된 항목은 공식 원문에서 확인하세요.'
    else:
        coverage_note = '상세 직무·자격·전형 정보가 부족합니다. 공식 공고문과 첨부파일을 먼저 확인하세요.'
    # 정보 충실도는 공고별 원본 자료 기준으로 표시합니다.
    available_facts = [
        label for label, present in (
            ('모집인원', bool(post.get('n'))),
            ('고용형태', bool(post.get('emp'))),
            ('학력조건', bool(post.get('edu'))),
            ('근무지역', bool(post.get('region'))),
            ('접수마감', bool(due)),
            ('상세 직무 설명', has_substantive_desc),
            ('지원 자격 상세', bool(qualification)),
            ('채용 절차 상세', bool(process)),
        ) if present
    ]
    missing_facts = [
        label for label in ('상세 직무 설명', '지원 자격 상세', '채용 절차 상세')
        if label not in available_facts
    ]
    completeness_html = (
        '<section aria-label="제공 정보 확인"><h2>제공 정보 확인</h2>'
        f'<p>현재 확인 가능한 항목: {escape(", ".join(available_facts) or "없음")}</p>'
        + (f'<p class="source-note">공식 원문에서 추가 확인할 항목: {escape(", ".join(missing_facts))}</p>' if missing_facts else '')
        + '</section>'
    )
    # 실제 담당업무는 ALIO 직무 분류만으로 추정할 수 없습니다.
    # 공식 공고/첨부 직무기술서에서 직접 확인할 질문을 안내합니다.
    duties_checklist_html = (
        '<section id="job-duties" aria-label="실제 담당업무 확인 안내">'
        '<h2>실제 담당업무는 어디서 확인하나요?</h2>'
        '<p>현재 수집된 ALIO 데이터에는 실제 수행 업무를 설명하는 독립적인 항목이 없습니다. '
        '직무 분류만으로 담당업무나 근무 조건을 단정하지 마세요.</p>'
        '<ol class="checks">'
        '<li>아래 공식 채용공고를 열고 첨부된 직무기술서 또는 모집분야별 설명을 찾으세요.</li>'
        '<li>담당업무·근무부서·근무장소와 교대근무 여부 등 실제 근무 조건을 확인하세요.</li>'
        '<li>자격요건과 우대조건이 지원하려는 모집분야에 적용되는지 구분하세요.</li>'
        '<li>직무기술서가 없거나 내용이 불명확하면 공고의 공식 문의처에 확인하세요.</li>'
        '</ol>'
        '<p class="source-note">이 안내는 공고별 업무를 추정한 설명이 아니라 공식 원문 확인을 돕는 점검표입니다.</p>'
        '</section>'
    )
    coverage_html = (
        '<section aria-label="공고 정보 제공 범위"><h2>공고 정보 제공 범위</h2>'
        f'<p class="source-note">{escape(coverage_note)}</p></section>'
    )

    extra = ''
    detail_anchors = []
    if isinstance(detail, dict):
        for key, label in DETAIL_LABELS.items():
            val = detail.get(key)
            if isinstance(val, str) and val.strip():
                # 긴 ALIO 원문을 임의로 1,500자에서 끊지 않습니다.
                # 화면에는 최대 6,000자를 제공하고 초과 시 누락을 명시합니다.
                visible = val[:6000]
                truncated = len(val) > len(visible)
                anchor = 'detail-' + key.lower()
                detail_anchors.append((anchor, label))
                extra += (
                    f'<section id="{anchor}"><h2>{escape(label)}</h2>'
                    f'<div class="detail-text">{escape(visible)}</div>'
                    + (
                        '<p class="source-note">이 항목은 원문이 길어 일부만 표시됩니다. '
                        '전체 내용은 반드시 공식 채용공고에서 확인하세요.</p>'
                        if truncated else ''
                    )
                    + '</section>'
                )

    toc_items = [
        ('job-summary', '모집 요약'),
        ('job-checks', '지원 전 확인'),
        ('job-duties', '담당업무 확인'),
        ('job-official', '공식 공고'),
    ] + detail_anchors
    toc_html = (
        '<nav class="job-toc" aria-label="채용공고 목차"><strong>목차 · 빠른 이동</strong><div>'
        + ''.join(f'<a href="#{escape(anchor, quote=True)}">{escape(label)}</a>' for anchor, label in toc_items)
        + '</div></nav>'
    )
    # 생성 시각을 삽입하면 매 실행마다 모든 HTML이 변경되므로 출처만 표시합니다.
    source_html = (
        '<p class="source-meta">자료 출처: ALIO 제공 데이터 · '
        '최신 수정·접수 정보는 반드시 공식 채용공고에서 확인하세요.</p>'
    )

    # 공고마다 고유한 확인 가능 정보로 설명을 구성합니다.
    # 직무 분류처럼 짧은 원본 설명만으로는 채용 내용을 설명하기 어렵습니다.
    desc = clean(post.get('desc'))
    summary_parts = [
        f'{org}의 {title} 채용공고입니다.',
        f'고용형태: {clean(post.get("emp"))}.' if post.get('emp') else '',
        f'근무지역: {clean(post.get("region"))}.' if post.get('region') else '',
        f'모집인원: {clean(post.get("n"))}명.' if post.get('n') else '',
        f'접수마감: {due_display}.' if due else '',
    ]
    # ALIO desc는 NCS 직무 분류이며 실제 담당업무가 아닙니다.
    is_category_only = bool(desc)
    if qualification:
        summary_parts.append('지원자격: ' + qualification[:900])
    if process:
        summary_parts.append('전형 절차: ' + process[:500])
    job_description = ' '.join(part for part in summary_parts if part)

    schema = {
        '@context': 'https://schema.org',
        '@type': 'JobPosting',
        'title': title,
        'description': job_description,
        'hiringOrganization': {
            '@type': 'Organization',
            'name': org,
        },
        'url': canonical,
    }

    posted = parse_date(post.get('pub'))
    if posted:
        schema['datePosted'] = posted

    if deadline:
        # Google's JobPosting accepts an ISO date alone when only the
        # application end date is known. Do not publish the synthetic 23:59
        # sorting timestamp as a verified closing time.
        schema['validThrough'] = (
            deadline[:10] if post.get('dueHasTime') is False else deadline
        )

    regions = list(dict.fromkeys(
        part.strip() for part in re.split(r'[,|]', clean(post.get('region')))
        if part.strip()
    ))
    if regions:
        # Google JobPosting requires separate Places for multiple locations.
        # Only split explicit source delimiters; never infer additional areas.
        locations = [{
            '@type': 'Place',
            'address': {
                '@type': 'PostalAddress',
                'addressCountry': 'KR',
                'addressRegion': region,
            },
        } for region in regions]
        schema['jobLocation'] = locations if len(locations) > 1 else locations[0]

    # ALIO 고용형태는 근로시간과 다른 분류입니다. 부분 문자열 검사로
    # '무기계약직'을 TEMPORARY로 잘못 분류하거나 복수 형태를 단정하지 않습니다.
    if post.get('emp'):
        raw_employment = post['emp']
        kinds = raw_employment if isinstance(raw_employment, list) else [raw_employment]
        unique_kinds = {clean(kind) for kind in kinds if clean(kind)}
        # 한 공고 안에 정규직·계약직이 같이 있으면 직무별 고용형태를 알 수 없어 생략.
        if len(unique_kinds) == 1:
            employment = next(iter(unique_kinds))
            employment_type = {
                '정규직': 'FULL_TIME',
                '계약직': 'TEMPORARY',
                '인턴': 'INTERN',
            }.get(employment)
            if employment_type:
                schema['employmentType'] = employment_type

    # 마감된 공고는 JobPosting 구조화 데이터를 제거합니다.
    # 안내용 HTML 페이지는 그대로 유지합니다.
    schema_json = '' if closed else (
        '<script type="application/ld+json">'
        + json.dumps(
            schema,
            ensure_ascii=False
        ).replace('<', '\\u003c')
        + '</script>'
    )

    notice = (
        '<p class="closed">'
        '접수 마감된 공고입니다. '
        '최신 모집 여부는 공식 공고를 확인하세요.'
        '</p>'
        if closed
        else ''
    )

    # 공식 원문 확인과 실제 지원 접수는 서로 다를 수 있습니다.
    # ALIO가 제공한 링크를 지원서 제출 URL로 오인하지 않도록 안내합니다.
    link = (
        '<section id="job-official" aria-label="공식 채용공고 확인">'
        '<h2>공식 원문 및 지원 방법 확인</h2>'
        '<p>지원 자격, 제출서류, 정확한 마감시각과 접수처는 공식 공고문을 기준으로 확인하세요. '
        '공식 공고 페이지에서 별도의 채용 접수 사이트로 이동해야 할 수 있습니다. '
        '링크 접속 오류(예: HTTP 400)가 발생하면 기관 채용 홈페이지에서 공고 제목으로 검색하거나, '
        '아래 ALIO 원본 링크를 이용하세요. 이 페이지는 링크의 실시간 접속 상태를 보증하지 않습니다.</p>'
        + (
            f'<a class="apply" href="{escape(official, quote=True)}" '
            f'rel="noopener noreferrer" target="_blank">'
            '공식 채용공고 열기 ↗</a>'
            if official
            else '<p class="source-note">공식 링크를 확인할 수 없습니다. 채용기관 홈페이지에서 공고를 검색하세요.</p>'
        )
        + (
            '<p class="source-note">기관 공고 페이지가 열리지 않으면 아래 ALIO 원본에서도 공고를 확인하세요. '
            '접수 가능 여부와 최종 제출처는 기관 공식 안내를 기준으로 판단해야 합니다.</p>'
            f'<a href="{escape(alio_reference, quote=True)}" rel="noopener noreferrer" '
            'target="_blank">ALIO 원본에서 공고 확인 ↗</a>'
            if alio_reference else ''
        )
        + '</section>'
    )

    meta_parts = [org, title]
    if post.get('region'):
        meta_parts.append('근무지역 ' + clean(post['region']))
    if post.get('emp'):
        meta_parts.append('고용형태 ' + clean(post['emp']))
    if due:
        meta_parts.append('접수마감 ' + due_display)
    meta_description = ' | '.join(meta_parts)[:155]

    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} | {escape(org)} | 커리어픽</title>
<meta name="description" content="{escape(meta_description, quote=True)}">
<link rel="canonical" href="{escape(canonical, quote=True)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{escape(title, quote=True)}">
<meta property="og:url" content="{escape(canonical, quote=True)}">
{schema_json}
<style>
body{{margin:0;background:#f5f7fb;color:#14213d;font:16px/1.7 system-ui,'Malgun Gothic',sans-serif}}
main{{max-width:720px;margin:35px auto;padding:24px;background:white;border-radius:18px;box-sizing:border-box}}
h1{{font-size:1.6rem;line-height:1.4}}
dt{{font-weight:700;color:#475569}}
dd{{margin:0 0 14px}}
.apply{{display:inline-block;background:#1f3fbf;color:white;padding:12px 20px;border-radius:9px;text-decoration:none}}
a{{color:#1f3fbf;text-underline-offset:3px}}
a:focus-visible{{outline:3px solid #f59e0b;outline-offset:3px;border-radius:3px}}
.skip-link{{position:absolute;left:12px;top:-100px;background:#fff;color:#14213d;padding:10px 14px;z-index:10}}
.skip-link:focus{{top:10px}}

.muted{{color:#64748b}}
.closed{{padding:12px;background:#fff1f2;color:#9f1239;border-radius:8px;font-weight:700}}
dl{{display:grid;grid-template-columns:minmax(100px,145px) 1fr;gap:8px 12px}}
dt,dd{{margin:0;padding:8px 0;border-bottom:1px solid #e5e7eb}}
section p{{white-space:pre-line;overflow-wrap:anywhere}}
.detail-text{{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.85;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px}}
section{{margin-top:24px}}
section h2{{margin-bottom:10px;line-height:1.45}}
@media(max-width:480px){{.detail-text{{padding:12px;font-size:0.96rem}}}}
.checks{{padding-left:22px}}
.checks li{{margin:10px 0}}
.related-jobs li{{margin:9px 0;overflow-wrap:anywhere}}
.source-note{{background:#f1f5f9;padding:12px 14px;border-radius:9px;color:#334155}}
.guide-links{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}
.guide-links a{{padding:8px 12px;border:1px solid #cbd5e1;border-radius:8px;text-decoration:none}}
.apply{{margin:12px 0}}
.job-toc{{margin:18px 0;padding:15px;background:#f1f5ff;border:1px solid #dbe4ff;border-radius:12px}}
.job-toc strong{{display:block;margin-bottom:9px}}
.job-toc div{{display:flex;flex-wrap:wrap;gap:8px}}
.job-toc a{{background:#fff;border:1px solid #c7d2fe;border-radius:999px;padding:7px 11px;text-decoration:none;font-size:13px;font-weight:700}}
.source-meta{{font-size:12px;color:#475569;border-left:3px solid #1f3fbf;padding:8px 12px;background:#f8fafc}}
html{{scroll-behavior:smooth}}
section[id],h2[id]{{scroll-margin-top:20px}}
@media(max-width:480px){{dl{{grid-template-columns:1fr;gap:0}}dt{{border:0;padding-bottom:0}}dd{{padding-top:0}}}}
@media(max-width:760px){{main{{margin:0;border-radius:0;padding:20px}}h1{{font-size:1.4rem}}section h2{{font-size:1.2rem}}.apply{{display:block;text-align:center;overflow-wrap:anywhere}}.guide-links a{{flex:1 1 auto;text-align:center}}}}
</style>
</head>
<body>
<a class="skip-link" href="#job-summary">본문으로 바로가기</a>
<main>
<nav><a href="/">← 커리어픽 전체 채용공고</a></nav>
<p class="muted">공공기관 채용정보</p>
<h1>{escape(title)}</h1>
<p>{escape(org)}</p>
{source_html}
{notice}
{toc_html}
<h2 id="job-summary">모집 요약</h2>
<dl>{rows}</dl>

{f'<section><h2>직무 분류</h2><p>{escape(desc)}</p><p class="muted">직무 분류는 실제 담당업무 설명이 아닙니다. 세부 직무는 공식 공고를 확인하세요.</p></section>' if is_category_only else ''}
<section id="job-checks" aria-label="지원 전 핵심 확인사항">
<h2>지원 전 핵심 확인사항</h2>
<ul class="checks">{checks}</ul>
</section>
{coverage_html}
{duties_checklist_html}
{completeness_html}
{detail_status}
{link}
{extra}
<hr>
<p class="muted">
본 페이지는 공공 채용정보를 요약한 안내 페이지입니다.
지원 전 반드시 공식 공고의 자격조건, 마감시각,
변경사항을 확인하세요.
</p>
<section aria-label="취업 준비 참고자료">
<h2>관련 취업 준비 자료</h2>
{guide_links}
</section>
{related_html}
<a href="/">다른 채용공고 찾아보기</a>
<footer aria-label="사이트 안내">
<p class="muted">커리어픽은 공식 채용공고를 안내하는 정보 서비스이며, 채용기관을 대신해 지원서를 접수하지 않습니다.</p>
<nav class="guide-links" aria-label="사이트 정책 및 연락처"><a href="/about.html">사이트 소개</a><a href="/privacy.html">개인정보처리방침</a><a href="/contact.html">문의하기</a></nav>
</footer>
</main>
</body>
</html>'''


def duplicate_key(post):
    """Conservative candidate key; never automatically delete ALIO postings."""
    values = tuple(
        re.sub(r'\s+', ' ', clean(post.get(field))).strip().casefold()
        for field in ('org', 'title', 'due')
    )
    return values if all(values) else None


def main():
    # Public restoration only: external-provider collection remains disabled.
    if not DATA.exists():
        raise SystemExit('alio.json 파일이 없습니다.')

    raw = json.loads(DATA.read_text(encoding='utf-8'))
    posts = (
        raw.get('posts', [])
        if isinstance(raw, dict)
        else []
    )

    details = (
        json.loads(DETAIL.read_text(encoding='utf-8'))
        if DETAIL.exists()
        else {}
    )

    if not isinstance(details, dict):
        details = {}

    if not posts:
        raise SystemExit(
            '공고 데이터가 비어 있어 기존 페이지를 보존합니다.'
        )

    OUT.mkdir(exist_ok=True)
    created = 0
    quality = {
        'total': 0,
        'with_category_only_description': 0,
        'with_qualification': 0,
        'with_process': 0,
        'with_both': 0,
        'with_description': 0,
        'without_official_link': 0,
        'thin_data': 0,
    }

    # 자동 품질 보고서: 검색 노출이나 채용공고 생성 여부는 변경하지 않습니다.
    quality_rows = []
    duplicate_groups = {}
    official_by_id = {}
    detail_field_counts = {}
    # 원본 데이터에 존재하는 동일 기관 공고만 연결합니다.
    # 정렬 기준은 마감일·ID로 고정해 반복 빌드 결과를 안정적으로 유지합니다.
    by_org = {}
    for item in posts:
        if not isinstance(item, dict) or not item.get('alio'):
            continue
        item_id = clean(item.get('id'))
        item_org = clean(item.get('org'))
        if re.fullmatch(r'a[0-9]+', item_id) and item_org and clean(item.get('title')):
            by_org.setdefault(item_org, []).append(item)
    for group in by_org.values():
        group.sort(key=lambda item: (clean(item.get('due')), clean(item.get('id'))))

    # 1. 잡알리오 채용공고 상세페이지 생성
    for post in posts:
        if not isinstance(post, dict) or not post.get('alio'):
            continue

        pid = clean(post.get('id'))
        if not re.fullmatch(r'a[0-9]+', pid):
            continue

        job_detail = details.get(pid, {})
        if not isinstance(job_detail, dict):
            job_detail = {}
        # 원본 API 상세 필드의 실제 제공률을 기록해 필드명 변경/누락을 탐지합니다.
        for field, value in job_detail.items():
            if clean(value):
                detail_field_counts[field] = detail_field_counts.get(field, 0) + 1
        has_qualification = bool(clean(job_detail.get('aplyQlfcCn')))
        has_process = bool(clean(job_detail.get('scrnprcdrMthdExpln')))
        # ALIO desc는 NCS 분류이므로 직무설명 충실도로 집계하지 않습니다.
        category_only = bool(clean(post.get('desc')))
        has_description = False
        quality['with_category_only_description'] += int(category_only)
        official_url = safe_url(post.get('src')) or safe_url(post.get('url'))
        has_official = bool(official_url)
        official_by_id[pid] = official_url
        quality['total'] += 1
        quality['with_qualification'] += int(has_qualification)
        quality['with_process'] += int(has_process)
        quality['with_both'] += int(has_qualification and has_process)
        quality['with_description'] += int(has_description)
        quality['without_official_link'] += int(not has_official)
        quality['thin_data'] += int(
            not has_qualification and not has_process and not has_description
        )

        missing = [
            name for name, present in (
                ('지원자격 상세', has_qualification),
                ('채용절차 상세', has_process),
                ('실질 직무설명', has_description),
                ('학력조건', bool(post.get('edu'))),
                ('접수마감', bool(post.get('due'))),
                ('공식링크', has_official),
            ) if not present
        ]
        # 같은 기관·제목·마감일은 중복 가능성만 진단합니다.
        # 동일 제목의 서로 다른 직무일 수 있어 게시물을 자동 삭제하지 않습니다.
        candidate_key = duplicate_key(post)
        if candidate_key:
            duplicate_groups.setdefault(candidate_key, set()).add(pid)
        quality_rows.append({
            'id': pid,
            'title': clean(post.get('title')),
            'organization': clean(post.get('org')),
            'official_link_host': (urlparse(official_url).hostname or '') if official_url else '',
            'official_link_status': 'url_format_ok_not_live_checked' if official_url else 'missing_or_invalid',
            'missing': missing,
            'detail_fields': {
                'qualification': has_qualification,
                'process': has_process,
                'substantive_description': has_description,
            },
        })

        target = OUT / f'{pid}.html'
        html = render(post, job_detail, by_org.get(clean(post.get('org')), ()))

        if (
            not target.exists()
            or target.read_text(encoding='utf-8') != html
        ):
            target.write_text(html, encoding='utf-8')
            created += 1

    # 2. 실제 존재하는 상세페이지 목록 생성
    # 홈페이지에서 없는 파일로 연결하지 않도록 사용
    available = sorted(
        p.stem
        for p in OUT.glob('a[0-9]*.html')
        if re.fullmatch(r'a[0-9]+', p.stem)
    )

    # 3. 홈페이지에서 읽을 JavaScript 목록 생성
    available_js = (
        'window.CAREERPICK_JOB_IDS = new Set('
        + json.dumps(available, ensure_ascii=False)
        + ');\n'
    )

    inventory = OUT / 'available.js'

    # 내용이 바뀌었을 때만 파일 갱신
    if (
        not inventory.exists()
        or inventory.read_text(encoding='utf-8') != available_js
    ):
        inventory.write_text(
            available_js,
            encoding='utf-8'
        )

    # 같은 기관·제목·마감일의 공고 ID만 보고서에 기록합니다.
    suspected_duplicates = []
    for key, ids in duplicate_groups.items():
        if len(ids) <= 1:
            continue
        links = sorted({official_by_id.get(pid, '') for pid in ids if official_by_id.get(pid)})
        suspected_duplicates.append({
            'organization': key[0], 'title': key[1], 'deadline': key[2],
            'ids': sorted(ids),
            'distinct_official_link_count': len(links),
            'source_link_comparison': (
                'different_official_links_review_separately' if len(links) > 1
                else 'same_official_link_review' if len(links) == 1
                else 'official_link_unavailable'
            ),
        })
    suspected_duplicates.sort(key=lambda item: (item['organization'], item['title'], item['deadline']))
    quality['suspected_duplicate_groups'] = len(suspected_duplicates)
    quality['duplicate_groups_with_distinct_official_links'] = sum(
        item['distinct_official_link_count'] > 1 for item in suspected_duplicates
    )
    # Source-field coverage helps distinguish a missing API field from a rendering defect.
    # Track the presence of an explicit description field, without treating
    # NCS category labels as a substantive account of actual duties.
    quality['substantive_description_source_available'] = sum(
        bool(clean(details.get(row['id'], {}).get('jobDscrptn')))
        for row in quality_rows
        if isinstance(details.get(row['id']), dict)
    )
    quality['missing_substantive_description'] = sum(
        '실질 직무설명' in row['missing'] for row in quality_rows
    )
    # Flag source-detail coverage changes without assuming missing data is a site bug.
    quality['source_qualification_coverage_pct'] = round(
        100 * quality['with_qualification'] / quality['total'], 1
    ) if quality['total'] else 0.0
    quality['source_process_coverage_pct'] = round(
        100 * quality['with_process'] / quality['total'], 1
    ) if quality['total'] else 0.0
    quality['source_duties_coverage_pct'] = round(
        100 * quality['substantive_description_source_available'] / quality['total'], 1
    ) if quality['total'] else 0.0
    quality['suspected_same_link_duplicate_groups'] = sum(
        item['distinct_official_link_count'] == 1 for item in suspected_duplicates
    )
    # JSON 보고서는 배포 중 자동 생성되며 공개 페이지에서는 링크하지 않습니다.
    report = {
        'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': 'ALIO',
        'summary': quality,
        'detail_field_counts': dict(sorted(
            detail_field_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )),
        'posts': quality_rows,
        'suspected_duplicates': suspected_duplicates,
    }
    report_path = ROOT / 'job-quality-report.json'
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(f'채용공고 품질 보고서: {report_path.name}')
    print('ALIO 상세 필드 제공 건수:', json.dumps(
        report['detail_field_counts'], ensure_ascii=False,
    ))

    # 읽기 전용 진단: 기존 생성·게시·색인 동작은 변경하지 않습니다.
    print('채용공고 원본 데이터 품질 진단:', json.dumps(quality, ensure_ascii=False))
    print(f'채용 상세페이지 생성/변경: {created}개')
    print(f'연결 가능한 상세페이지: {len(available)}개')
    print('상세페이지 연결 목록: jobs/available.js')


def self_test():
    """Offline regression checks; never reads production data or publishes posts."""
    sample = {
        'id': 'a12345', 'title': '<script>test</script>', 'org': '테스트기관',
        'due': '2099-10-28', 'n': 3, 'alio': True,
        'src': 'https://job.alio.go.kr/example',
    }
    html = render(sample, {'aplyQlfcCn': '지원 자격 확인'})
    # Structured-data regression: canonical, publisher, deadline and safe title.
    schema_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert schema_match, 'Active job must expose JobPosting JSON-LD'
    schema_data = json.loads(schema_match.group(1))
    assert schema_data['@type'] == 'JobPosting'
    assert schema_data['title'] == sample['title']
    assert schema_data['hiringOrganization']['name'] == sample['org']
    assert schema_data['url'] == BASE + '/jobs/a12345.html'
    assert schema_data['validThrough'], 'Active job must carry a known deadline'
    # ALIO reports a date but not a verified closing time.
    date_only = dict(sample, due='2099-10-29T23:59:00+09:00', dueHasTime=False)
    date_only_html = render(date_only, {})
    assert '<dt>접수마감</dt><dd>2099-10-29</dd>' in date_only_html
    assert '2099-10-29 23:59' not in date_only_html
    date_only_jsonld = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        date_only_html, re.S
    )
    assert date_only_jsonld
    assert json.loads(date_only_jsonld.group(1))['validThrough'] == '2099-10-29'
    with_verified_time = dict(date_only, dueHasTime=True)
    with_time_html = render(with_verified_time, {})
    assert '<dt>접수마감</dt><dd>2099-10-29 23:59</dd>' in with_time_html
    with_time_jsonld = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        with_time_html, re.S
    )
    assert with_time_jsonld
    assert json.loads(with_time_jsonld.group(1))['validThrough'] == '2099-10-29T23:59:00+09:00'
    # EmploymentType is not a substring search: 무기계약직 is NOT TEMPORARY,
    # 비정규직 is NOT 정규직, and mixed categories must not be guessed.
    for employment, expected in (
        (['정규직'], 'FULL_TIME'),
        (['계약직'], 'TEMPORARY'),
        (['인턴'], 'INTERN'),
        (['무기계약직'], None),
        (['비정규직'], None),
        (['정규직', '계약직'], None),
    ):
        candidate = dict(sample, emp=employment)
        candidate_html = render(candidate, {})
        candidate_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', candidate_html, re.S
        )
        assert candidate_match, 'Current recruitment must have JobPosting data'
        candidate_schema = json.loads(candidate_match.group(1))
        assert candidate_schema.get('employmentType') == expected, (
            f'Invalid employmentType for {employment}: {candidate_schema.get("employmentType")}'
        )
    assert '<script>test</script>' not in schema_match.group(1)
    assert html.count('type="application/ld+json"') == 1
    for marker in (
        'id="job-summary"', 'id="job-checks"', 'id="job-duties"',
        'id="job-official"', 'href="#job-official"',
        '자료 출처: ALIO', 'https://job.alio.go.kr/example',
        '&lt;script&gt;test&lt;/script&gt;',
    ):
        assert marker in html, f'누락된 페이지 요소: {marker}'
    for unsafe in (
        'javascript:alert(1)', 'https://localhost/private',
        'https://192.168.1.1/private', 'https://example.com:bad/path',
        'https://user:pass@example.com/',
        'https://[broken-ipv6/private',
    ):
        assert not safe_url(unsafe), f'위험 URL 허용: {unsafe}'
    assert safe_url('https://job.alio.go.kr/example')
    assert duplicate_key({'org': ' A 기관 ', 'title': '채용  공고', 'due': '2099-01-01'}) == duplicate_key(
        {'org': 'a 기관', 'title': '채용 공고', 'due': '2099-01-01'}
    )
    assert duplicate_key({'org': 'A', 'title': '공고', 'due': ''}) is None
    assert duplicate_key({'org': 'A', 'title': '공고', 'due': '2099-01-01'}) != duplicate_key(
        {'org': 'A', 'title': '공고', 'due': '2099-01-02'}
    )
    # 관련 공고는 실제 동일 기관 목록만 연결하고 자기 자신은 제외합니다.
    related = [
        {'id': 'a12345', 'title': '현재 공고', 'due': '2099-10-28'},
        {'id': 'a12346', 'title': '<b>다른 공고</b>', 'due': '2099-11-01'},
        {'id': 'invalid', 'title': '잘못된 ID'},
    ]
    related_html = render(sample, {}, related)
    assert '/jobs/a12346.html' in related_html
    assert '&lt;b&gt;다른 공고&lt;/b&gt;' in related_html
    assert 'href="/jobs/a12345.html"' not in related_html
    assert 'href="/jobs/invalid.html"' not in related_html
    assert '같은 기관의 다른 채용공고' not in render(sample, {})
    # 기관 공고와 ALIO 링크가 다를 때만 보조 경로를 표시합니다.
    sample['src'] = 'https://agency.example.org/recruit/123'
    sample['url'] = 'https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=123'
    fallback_html = render(sample, {})
    assert 'ALIO 원본에서 공고 확인' in fallback_html
    assert 'HTTP 400' in fallback_html
    assert '실시간 접속 상태를 보증하지 않습니다' in fallback_html
    assert 'https://agency.example.org/recruit/123' in fallback_html
    sample['url'] = sample['src']
    assert 'ALIO 원본에서 공고 확인' not in render(sample, {})
    sample['url'] = 'javascript:alert(1)'
    assert 'ALIO 원본에서 공고 확인' not in render(sample, {})
    # 공식 URL이 없거나 안전하지 않으면 지원 버튼을 만들지 않습니다.
    sample['src'] = 'https://192.168.1.2/private'
    sample['url'] = 'javascript:alert(1)'
    unsafe_html = render(sample, {})
    assert '공식 링크를 확인할 수 없습니다' in unsafe_html
    assert 'href="javascript:' not in unsafe_html
    assert 'href="https://192.168.1.2' not in unsafe_html
    # 마감 공고에는 접수 종료 안내를 제공하고 JobPosting 스키마를 제외합니다.
    sample['src'] = 'https://job.alio.go.kr/example'
    sample['due'] = '2020-01-01'
    closed_html = render(sample, {})
    assert '접수 마감된 공고입니다' in closed_html
    assert 'type="application/ld+json"' not in closed_html
    # 동일한 입력은 동일한 HTML을 생성해야 합니다.
    assert render(sample, {}) == closed_html
    print('CareerPick job-page regression checks: PASS')


if __name__ == '__main__':
    import sys
    if '--self-test' in sys.argv:
        self_test()
    else:
        main()



