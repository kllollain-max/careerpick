
"""Generate searchable static ALIO job pages for CareerPick.

Run from the repository root: python scripts/build_job_pages.py
"""

import ipaddress
import hashlib
import json
import re
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote, urlparse

try:
    from scripts.notice_review import fingerprint as notice_fingerprint, resolve as resolve_notice_reviews
except ModuleNotFoundError:
    from notice_review import fingerprint as notice_fingerprint, resolve as resolve_notice_reviews

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'alio.json'
DETAIL = ROOT / 'alio-detail.json'
OUT = ROOT / 'jobs'
BASE = 'https://kllollain-max.github.io/careerpick'
CONFIRMED_APPLICATION_CUTOFFS = {
    # Official KINS notice image, section7, directly read 2026-11-23.
    'a307238': '2026-12-04T18:00:00+09:00',
    # Separate Yangyang/Samcheok HWPX originals, sectionIII (not publication-end clocks).
    'a307298': '2026-12-04T18:00:00+09:00',
    'a307299': '2026-12-04T18:00:00+09:00',
    # Official KLI PDF section4 and KIET PDF section5 (24:00 is next-day00:00).
    'a306470': '2026-12-10T16:00:00+09:00',
    'a307170': '2026-12-10T00:00:00+09:00',
    # Official KHNP recruitment PDF 3089063 p9; school recommendation has a different deadline.
    'a307284': '2026-12-08T15:00:00+09:00',
    # Official notice originals, read 2026-11-18; postal reception opens 11/24.
    'a307150': '2026-12-01T10:00:00+09:00',
    'a307151': '2026-12-01T10:00:00+09:00',
    'a306988': '2026-12-01T18:00:00+09:00',
    # Bohun Hospital official full recruitment notice (2026-11-20):
    # 11/20 17:00 KST, in-person at the education/training office.
    'a306992': '2026-11-20T17:00:00+09:00',
    # SNUBH employer recruiting portal (jobnoticeSn=271976), reviewed 2026-11-20:
    # applications 11/11 09:00 - 11/20 23:59 KST; not the ALIO publication clock.
    'a306874': '2026-11-20T23:59:00+09:00',
    # PNUH recruitment PDF 3088502 p3: online applications through 12/03 17:00 KST.
    'a307225': '2026-12-03T17:00:00+09:00',
    'a306937': '2026-11-20T17:00:00+09:00',
    'a306941': '2026-11-20T17:00:00+09:00',
    'a306962': '2026-11-20T17:00:00+09:00',
    # CNUH original recruitment PDFs (ALIO fileNo 3085307/3085325/3085331)
    # read 2026-11-19. All three require submission by 17:00 on 11/19,
    # NOT the synthetic 23:59 ALIO publication-end clock.
    'a306733': '2026-11-19T17:00:00+09:00',
    'a306735': '2026-11-19T17:00:00+09:00',
    'a306737': '2026-11-19T17:00:00+09:00',
    # ALIO official detail (not publication end), checked 2026-11-17.
    'a306755': '2026-11-20T17:00:00+09:00',
    # SNU Dental Hospital official notice: reception opens 2027-01-18 09:00.
    'a306925': '2027-01-22T18:00:00+09:00',
    # CNUH official recruitment portal (its own ALIO a306942 notice), checked 2026-11-17.
    'a306942': '2027-01-22T17:00:00+09:00',
    # Official Nara Iltter KIOST notice 308183: end of application, not ALIO 23:59.
    'a306913': '2026-11-26T10:00:00+09:00',
    'a306545': '2026-11-17T17:00:00+09:00',
    'a306512': '2026-11-12T15:00:00+09:00',
    'a306648': '2026-11-12T15:00:00+09:00',
    # Official HWP originals, checked 2026-11-17; not ALIO publication end times.
    'a306334': '2026-11-09T18:00:00+09:00',
    'a306653': '2026-11-09T18:00:00+09:00',
    'a306548': '2026-11-17T17:00:00+09:00',
    'a306553': '2026-11-17T17:00:00+09:00',
    'a306750': '2026-11-19T10:00:00+09:00',
    'a306355': '2026-11-16T10:00:00+09:00',
    'a306799': '2026-11-23T10:00:00+09:00',
    'a306662': '2026-11-18T17:00:00+09:00',
    # CBNHU official application portal: 2026-11-18 12:00, not ALIO's 23:59 posting end.
    # KOPO employer notice 790549: registered mail or weekday visit must arrive by 18:00.
    # This is not the ALIO posting-end 23:59; no feed mutation.
    'a307171': '2026-11-25T18:00:00+09:00',
    'a306665': '2026-11-18T12:00:00+09:00',
    # Official ALIO recruitment method: 2026-11-18 17:00, not the 23:59 posting end.
    'a306660': '2026-11-18T17:00:00+09:00',
    # Official JOB-ALIO detail 306718: Gwangju Veterans Hospital reception ends at 10:00, not ALIO's 23:59 posting end.
    'a306718': '2026-11-18T10:00:00+09:00',
    # Official 307034 notice HWP, section 6; ALIO fileNo=3087622, checked 2026-11-16.
    'a307034': '2026-11-20T16:00:00+09:00',
    # Official notice originals: HWP 3085542 section 6; PDF 3087571 page 2.
    'a306774': '2026-11-17T13:00:00+09:00',
    'a307061': '2026-11-30T18:00:00+09:00',
    # Official 2026 notices: PNG 3087597; PDFs 3086097 and 3087307.
    'a307067': '2026-12-01T15:00:00+09:00',
    'a306816': '2026-11-25T18:00:00+09:00',
    'a307024': '2026-11-30T10:00:00+09:00',
}
VERIFIED_DUTIES = json.loads(
    (Path(__file__).with_name('verified_job_duties.json')).read_text(encoding='utf-8')
) if Path(__file__).with_name('verified_job_duties.json').exists() else {}

# ALIO official detailed recruitment text, not an independently read PDF/HWP
# job-duty original. Keep this proof separate from VERIFIED_DUTIES counts.
VERIFIED_APPLICATION_NOTICES = {
    'a307238': {'organization': '한국원자력안전기술원',
     'title': '한국원자력안전기술원 2027년 상반기 정규직 직원 채용',
     'source_end_date': '2026-12-04',
     'expected_source_seats': '30',
     'source_employment': ['정규직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3088729',
     'checked_on': '2026-11-23',
     'scope': '공식 모집표의 전형별 인원·학력·필수자격·접수일정',
     'role_mix_note': 'ALIO 수집 인원은30명이지만 공식 첨부 모집표는 일반채용29명·국가보훈 제한경쟁2명·필수면허 제한경쟁1명으로 합계32명입니다. 두 '
                      '수치를 임의로 합산하거나 모두 같은 지원조건으로 보지 말고 기관 최신 정정 공고에서 확정 인원을 확인하세요. 연구직의 대다수 분야는 '
                      '석사 이상, 정보기술은 학사 이상이며 경영관리는 학력 제한이 없습니다. 공통 영어성적 기준·면제 조건과 분야별 필수자격은 각각 '
                      '확인해야 합니다.',
     'hiring_breakdown': '공식 첨부: 일반29명 + 보훈2명 + 필수면허1명 = 32명 · ALIO 수집30명과 불일치',
     'hiring_breakdown_label': '공식 모집표와 수집 인원의 차이',
     'source_headcount_conflict': True,
     'regular_review_hold_due_to_mixed_role_units': True,
     'application_start': '2026-11-19',
     'application_end_date': '2026-12-04'},
    'a307298': {'organization': '주택관리공단(주)',
     'title': '육아휴직 대체직 채용공고(주택관리공단 강원지사)',
     'source_end_date': '2026-12-04',
     'expected_source_seats': '1',
     'source_employment': ['계약직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3089175',
     'checked_on': '2026-11-23',
     'application_start': '2026-11-20',
     'application_end_date': '2026-12-04',
     'scope': '공식 HWPX의 모집표·계약기간·원서접수 일정',
     'hiring_breakdown': '양양권역 관리소(3군단영동주거지원센터) 기술직 육아휴직 대체직 1명',
     'role_mix_note': '양양권역 관리소(3군단영동주거지원센터)의 별도 기술직1명 모집으로 계약 종료 예정일은2027년12월14일입니다. 기간 만료 후 '
                      '고용관계가 소멸되는 대체직이며 정규직 전환을 보장하는 공고가 아닙니다. 원서접수는 2026년11월20일~12월4일18시까지 온라인 '
                      '접수로 안내합니다. 다른 권역 공고와 근무지·계약기간을 혼용하지 마세요. 원문에는 행정·기술 직무요건 공통표가 함께 있지만 이 '
                      '모집표의 선발 직무는 기술직입니다.'},
    'a307299': {'organization': '주택관리공단(주)',
     'title': '육아휴직 대체직 채용공고(주택관리공단 강원지사)',
     'source_end_date': '2026-12-04',
     'expected_source_seats': '1',
     'source_employment': ['계약직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3089178',
     'checked_on': '2026-11-23',
     'application_start': '2026-11-20',
     'application_end_date': '2026-12-04',
     'scope': '공식 HWPX의 모집표·계약기간·원서접수 일정',
     'hiring_breakdown': '삼척권역 관리소(주거행복지원센터) 기술직 육아휴직 대체직 1명',
     'role_mix_note': '삼척권역 관리소(주거행복지원센터)의 별도 기술직1명 모집으로 계약 종료 예정일은2028년1월3일입니다. 기간 만료 후 고용관계가 '
                      '소멸되는 대체직이며 정규직 전환을 보장하는 공고가 아닙니다. 원서접수는 2026년11월20일~12월4일18시까지 온라인 접수로 '
                      '안내합니다. 다른 권역 공고와 근무지·계약기간을 혼용하지 마세요. 원문에는 행정·기술 직무요건 공통표가 함께 있지만 이 모집표의 선발 '
                      '직무는 기술직입니다.'},
    'a306012': {'organization': '한국개발연구원',
     'title': 'KDI 연구위원급 채용 공고',
     'source_end_date': '2026-12-02',
     'expected_source_seats': '8',
     'source_employment': ['정규직'],
     'source_url': 'https://econjobmarket.org/positions/12824',
     'checked_on': '2026-11-23',
     'scope': '경제 전반의 정책 연구·자료 분석·연구보고서 작성',
     'role_mix_note': '세종 근무 부연구위원 8명 모집으로, 경제학 또는 관련 분야 박사학위 소지자나 2027년 8월 말까지 취득예정자가 대상입니다. 최초 '
                      '임용계약은 3년이며 연구실적·평가에 따라 재임용이 거부될 수 있습니다. 추천서 3부와 이력서·연구논문을 준비하세요. 원문 HWP는 '
                      '12월 2일 24:00 UTC, EJM은 12월 2일 midnight UTC로 표현하므로 한국시간 23:59로 바꾸지 말고 접수처에 '
                      '정확한 시각을 확인하세요.',
     'utc_application_window_label': '2026-12-02 24:00 UTC(공고문) · 12월2일 midnight UTC(EJM); 한국시간 '
                                     '종료시각 기관 확인 필요'},
    'a306470': {'organization': '한국노동연구원',
     'title': '한국노동연구원 연구위원 직군 채용 공고',
     'source_end_date': '2026-12-10',
     'expected_source_seats': '6',
     'source_employment': ['정규직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3083482',
     'checked_on': '2026-11-23',
     'scope': '노동·인사조직·노사관계 분야의 연구 기획·진행·관리',
     'role_mix_note': '노동시장·불평등·정책분석 3명과 인사조직관리·노사관계·산업안전·산재보험 3명, 총6명입니다. 모집분야 박사 또는 2027년 8월 말까지 '
                      '취득 조건, 채용예정일 기준 만60세 이내와 남성 공고일 기준 군필·면제 조건을 확인하세요. 지원서와 추천서 2건 모두 '
                      '2026년12월10일16시(KST)까지입니다.',
     'hiring_breakdown': '노동시장·불평등·정책분석 3명 · 인사조직관리·노사관계·산업안전·산재보험 3명 = 총6명'},
    'a307170': {'organization': '산업연구원',
     'title': '2027년 박사학위(예정)자 채용 공고(부연구위원 직급)',
     'source_end_date': '2026-12-09',
     'expected_source_seats': '6',
     'source_employment': ['정규직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3088222',
     'checked_on': '2026-11-23',
     'scope': '산업정책·산업전환·통상·경제전망·지역경제 연구',
     'role_mix_note': '경제학 전 분야 부연구위원 총6명입니다. 경제학 또는 관련 분야 박사 취득자·예정자가 대상이며 예정자는 임용일 전에 학위를 취득해야 '
                      '합니다. 남성은 공고일 현재 군필·면제, 임용일부터 현업 전일근무 가능, 임용예정일 기준 만60세 미만 조건을 확인하세요. 공고문 원문 '
                      '마감은 2026년12월9일24:00 한국시간으로, 다음 날 12월10일00:00(KST)과 같은 시각입니다.',
     'application_end_date': '2026-12-10'},
    'a299289': {'organization': '부산대학교병원',
     'title': '2025년도 일반직(약무직) 신규직원 블라인드 공개채용 상시모집 공고(양산)',
     'source_end_date': '2026-12-31',
     'expected_source_seats': '10',
     'source_employment': ['정규직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3043002',
     'checked_on': '2026-11-23',
     'scope': '양산 약무직 대표 업무: 처방 검토·조제·약품정보·교육',
     'role_mix_note': '최초 모집 10명은 현재 남은 결원 수가 아닙니다. 약사 면허 소지자 또는 2026년 취득예정자가 대상이며 면허 취득 후3년 경과자는 '
                      '원문이 요구하는 면허신고 확인증을 점검하세요. 충원 시까지 모집 공고이나 현재 연결된 개별 접수 링크는 2026년11월23일 '
                      'HTTP404였으므로 현재 접수 활성과 잔여인원은 확인되지 않았습니다.',
     'application_status_unconfirmed': True,
     'conditional_application_window_label': '충원 시까지 (현재 접수 활성·잔여 인원 미확인)'},
    'a294598': {'organization': '경상국립대학교병원',
     'title': '[창원경상국립대학교병원] 약무직 채용 공고',
     'source_end_date': '2026-12-31',
     'expected_source_seats': '8',
     'source_employment': ['정규직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3016764',
     'checked_on': '2026-11-23',
     'scope': '창원 약무직 대표 업무: 조제·약품관리·임상약료',
     'role_mix_note': '공식 최초 인원은8명 이내로 현재 잔여 결원8명을 뜻하지 않습니다. 약사 면허 또는2026년 면허 취득예정, 원서접수 마감일 현재 '
                      '만20세 이상60세 미만과 남성 군필·면제 조건을 확인하세요. 2025년10월17일부터 충원 시까지 공고이며 현재 해당 공고의 접수 '
                      '활성은 확인되지 않았습니다.',
     'application_status_unconfirmed': True,
     'conditional_application_window_label': '충원 시까지 (현재 접수 활성·잔여 인원 미확인)'},
    'a307227': {'organization': '에너지경제연구원',
     'title': '[에너지경제연구원] 2027년도 상반기 정규직(부연구위원 이상) 채용공고',
     'source_end_date': '2026-12-11',
     'expected_source_seats': '5',
     'source_employment': ['정규직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3088653',
     'checked_on': '2026-11-23',
     'scope': '에너지·자원·국제협력 정책 연구: 일반 분야',
     'role_mix_note': '5명 이내의 일반 분야 연구직 모집입니다. 관련 전공 박사(2027년 9월 이내 취득예정 포함) 요건과 2027년 8월까지 입사 가능 조건이 '
                      '함께 있어 본인의 학위 일정 적용은 기관에 확인하세요. 처음부터 무조건 정규 임용되는 방식이 아니라 초임계약 1년 후 평가를 통한 정규직 '
                      '임용입니다. 원문은 12월 11일까지로 날짜만 명시하므로 정확한 마감시각·시간대는 공식 접수처 확인이 필요합니다.',
     'hiring_breakdown': '일반 분야 부연구위원 이상 5명 이내 · 초임계약 1년 후 평가를 통한 정규직 임용'},
    'a307284': {'organization': '한국수력원자력(주)',
     'title': '2026년도 제5차 신입사원(고졸수준) 선발',
     'source_end_date': '2026-12-08',
     'expected_source_seats': '40',
     'source_employment': ['정규직'],
     'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3089063',
     'checked_on': '2026-11-23',
     'scope': '기계 16명·전기전자 24명: 발전설비 정비',
     'role_mix_note': '기계16명과 전기전자24명, 합계40명입니다. 누구나 지원하는 일반 고졸채용이 아니라 2026년 현재 마이스터고 또는 원전 소재 기초자치단체 '
                      '내 특성화고의 해당 관련학과 2학년 재학생 중 학교장 추천을 받은 지원자가 대상입니다. 학교 추천서류 마감은 11월 23일, 추천받은 지원자의 '
                      '입사지원서 마감은 12월 8일 15시로 서로 다릅니다.',
     'hiring_breakdown': '기계 16명 · 전기전자 24명 = 총40명',
     'application_start': '2026-11-23',
     'application_end_date': '2026-12-08'},
    # CNUH original recruitment notice PDFs read as text 2026-11-19.
    # PDF originals independently acquired and SHA256 checked again 2026-11-19.
    # Exact-source records prevent stale cutoff/field facts after ALIO changes.
    'a306733': {
        'organization': '충남대학교병원',
        'title': '[대전] 2026년 11월 충남대학교병원 업무지원직(기계기사, 전기기사, 보조원, 환경사) 공개채용 공고',
        'source_end_date': '2026-11-19',
        'expected_source_seats': '21',
        'source_employment': ['정규직'],
        'application_start': '2026-11-05',
        'application_end_date': '2026-11-19',
        'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3085307',
        'notice_source_sha256': 'd7282d69cb886e8ed87b6909b02d9c3156a1b8b36635b7934950cf0881922ea3',
        'checked_on': '2026-11-19',
        'hiring_breakdown': '기계기사 1명, 전기기사 1명, 보조원 6명, 환경사 13명 (공식 공고문 전체 21명)',
        'scope': '공식 공고문 PDF 텍스트에서 11월 19일 17시 온라인 원서접수 마감, 직종별 1+1+6+13명, 기계·전기 필수 자격증과 보조원·환경사 별도 필수자격 없음, 3개월 수습 및 평가를 대조함. 공식 PDF 바이너리를 별도로 확보하고 SHA256을 재계산함.',
    },
    'a306735': {
        'organization': '충남대학교병원',
        'title': '[대전,세종] 2027년도 상반기 신규의료진(임상교수요원) 공개채용 모집공고',
        'source_end_date': '2026-11-19',
        'expected_source_seats': '49',
        'source_employment': ['정규직'],
        'application_start': '2026-11-05',
        'application_end_date': '2026-11-19',
        'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3085325',
        'notice_source_sha256': 'cf5231d2d88c7645191c8dffe2c922b8408bdbaf6564d21154aa6d11037eeab2',
        'checked_on': '2026-11-19',
        'scope': '공식 임상교수요원 모집 PDF 텍스트에서 대전·세종 전체 49명 및 11월 19일 17시 온라인 접수마감 확인. 분야별 상세인원과 실제 잔여 모집인원은 별도 검증하지 않음. 공식 PDF 바이너리를 별도로 확보하고 SHA256을 재계산함.',
    },
    'a306737': {
        'organization': '충남대학교병원',
        'title': '[대전,세종] 2027년도 상반기 신규의료진(전임의사) 공개채용 모집공고',
        'source_end_date': '2026-11-19',
        'expected_source_seats': '29',
        'source_employment': ['정규직'],
        'application_start': '2026-11-05',
        'application_end_date': '2026-11-19',
        'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3085331',
        'notice_source_sha256': '794581a4c4239ceb707358d2245685c96239e64fbcbb0f442df7c8274fcf54a1',
        'checked_on': '2026-11-19',
        'scope': '공식 전임의사 모집 PDF 텍스트에서 대전·세종 전체 29명, 지원 시 해당 진료과 전문의 자격 및 11월 19일 17시 온라인 접수마감 확인. 분야별 인원과 현재 실제 접수화면은 별도 미검증, 공식 PDF 바이너리를 별도로 확보하고 SHA256을 재계산함.',
    },
    # KNUH continuous pharmacist recruitment: official institution notice and
    # archived ALIO notice/duty originals byte-SHA checked 2026-11-19; the
    # duty PDF's first page was visually reviewed. Still conditional reception;
    # confirmation that 11 independent vacancies remain open today.
    # Direct SNUBH hiring-portal public notice read 2026-11-20, not the PDF's date-only table.
    # Public viewing of the application window does not prove a completed applicant submission.
    'a306874': {
        'reader_scope': '병원 공식 채용시스템에서 미화 10명과 11월 20일 23:59 접수마감을 확인했습니다. 현재 종료된 접수입니다.',
        'organization': '분당서울대학교병원',
        'title': '분당서울대학교병원 신입(업무지원직_미화) 직원 채용 공고',
        'source_end_date': '2026-11-20',
        'expected_source_seats': '10',
        'source_employment': ['정규직'],
        'application_start': '2026-11-11',
        'application_end_date': '2026-11-20',
        'source_url': 'https://snubh.recruiter.co.kr/app/jobnotice/view?jobnoticeSn=271976&systemKindCode=MRS2',
        'checked_on': '2026-11-20',
        'scope': ('분당서울대학교병원 공식 채용시스템 공고 271976의 2026-11-11 09:00부터 '
                  '2026-11-20 23:59 KST까지 온라인 접수 표기, 업무지원직 미화 AA1 10명 '
                  '공개 모집표 확인. 로그인 후 최종 제출 성공·현재 잔여 결원은 독립 검증하지 않음.'),
    },
    'a306182': {
        'reader_scope': '약사 면허·최초 예정인원 11명·충원 시 종료 조건을 확인했습니다. 현재 접수 가능 여부와 남은 인원은 확인되지 않았습니다.',
        'organization': '경북대학교병원',
        'title': '2026년도 약무직 공개채용 수시모집',
        'source_end_date': '2026-12-31',
        'expected_source_seats': '11',
        'source_employment': ['정규직'],
        'source_url': 'https://www.knuh.kr/content/04information/02_01.asp?b_num=7452&proc_type=view',
        'checked_on': '2026-11-19',
        # This is an until-filled notice; the original 11 seats do NOT prove
        # present reception or remaining vacancies. Keep the useful page,
        # but exclude it from indexed/current regular recommendations.
        'application_status_unconfirmed': True,
        'conditional_application_window_label': (
            '2026-04-01부터 충원 시까지 (공고 효력은 2026-12-31까지; '
            '현재 접수 활성·잔여 인원 미확인)'
        ),
        'role_mix_note': (
            '경북대학교병원 2026년도 정규직 약무직 수시모집 공고의 11명은 '
            '최초 채용 예정 인원입니다. 필수 지원자격은 약사 면허증 소지이며 '
            '본원 정년 규정에 따라 만 60세 이상 지원은 제한됩니다. '
            '원서접수는 2026년 4월 1일부터 예정인원 충원 시까지이고 '
            '공고 자체의 효력은 2026년 12월 31일까지입니다. '
            '공고 효력 종료일은 모든 11명이 그날까지 남아 있거나 '
            '온라인 접수가 그날 23:59까지 열린다는 뜻이 아닙니다. '
            '원문에 따르면 지원 순서에 따라 개별 전형을 진행하며 '
            '예정인원 충원 후 접수자의 전형은 진행하지 않을 수 있습니다. '
            '서류전형·면접·기재사항 증빙 확인 및 온라인 인성검사 절차를 '
            '따르므로, 공식 지원화면에서 현재 접수 가능 여부와 '
            '잔여 인원·수정 공고를 확인한 뒤 지원하세요. '
            '해당 병원의 다른 약무직 과거·추가 공고와 인원을 자동 합산하거나 '
            '약사의 구체적인 배치 부서·업무를 근거 없이 추정하지 않습니다.'
        ),
        'scope': (
            '2026-11-19 기관 공식 2026년 약무직 수시모집 HTML 게시글과 '
            '공식 공고 PDF 3039457의 공개 추출 텍스트로 11명·약사면허·'
            '충원 시 종료/공고효력 12월 31일·개별 전형을 대조함. '
            '보존 공고 PDF3081708 및 직무 PDF3081710의 SHA256을 독립 대조하고 '
            '직무 PDF 1쪽을 육안 판독하여 대표 약무업무를 검증함. '
            '실시간 채용사이트 접수 활성·잔여인원은 여전히 미확인. '
            '이전 별도 기관 PDF3039457의 403과 이번 보존 원본검증을 혼동하지 않음.'
        ),
    },
    # JOB-ALIO official notice HTML directly checked 2026-11-19.
    # Recruitment JPG 3087104 was visually checked, and duty HWP 3087106
    # SHA/BodyText read from the archived original. Scope only as explicitly
    # written in NCS duty description; no detailed clinical tasks inferred.
    'a306992': {
        'reader_scope': '보철·치주·보존과 합계 11명과 11월 20일 17시 방문접수 마감을 확인했습니다. 특정 치과 시술 업무는 원문에 명시되지 않았습니다.',
        'organization': '한국보훈복지의료공단',
        'title': '[중앙보훈병원]2027년 치과의사전공의(레지던트1년차) 채용공고',
        'source_end_date': '2026-11-20',
        'expected_source_seats': '11',
        'source_employment': ['정규직'],
        'source_url': 'https://www.bohun.or.kr/seoul/na/ntt/selectNttInfo.do?mi=32253&bbsId=1158&bbsSysId=seoul&nttSn=191258',
        'checked_on': '2026-11-20',
        'application_start': '2026-11-16',
        'application_end_date': '2026-11-20',
        'role_mix_note': (
            '중앙보훈병원 치과 레지던트 1년차 공고의 전체 모집 11명은 '
            '보철과 5명, 치주과 3명, 보존과 3명의 합계입니다. '
            '지원자는 인턴 기수료자 또는 2027년 2월 수료예정자여야 하며, '
            '의무사관후보생의 수련 완료 연령 조건과 공단 인사규정·성범죄 취업제한 '
            '결격사유를 확인해야 합니다. 다른 수련병원(기관)에 중복 지원·응시할 수 없습니다. '
            '공식 ALIO의 실제 서류 접수기간은 2026년 11월 16~20일이고 '
            '접수방법은 중앙보훈병원 교육수련부 방문 제출입니다. '
            '11월 29일 공동 필기시험, 12월 2일 면접, 12월 4일 합격 발표 예정이며 '
            '기관 공지로 변경될 수 있습니다. 중앙보훈병원 공식 채용공고의 '
            '전형일정표에서 2026년 11월 20일 17:00(KST)까지 '
            '교육수련부(제3관 2층) 방문접수로 명시합니다. '
            'ALIO 게시 종료시각 23:59를 방문접수 마감으로 혼동하지 마세요. '
            '실제 방문 서류제출 완료는 독립 확인하지 않았습니다. '
            '공고 JPG 원본은 육안 판독하고 직무 HWP의 원본 SHA256과 '
            'BodyText를 대조했습니다. 직무수행내용은 공공의료 관련 업무와 '
            '기타 행정업무만 명시하며, 개별 치과 시술을 추가 추정하지 않습니다.'
        ),
        'scope': (
            'JOB-ALIO a306992 공식 HTML 직접 재조회 2026-11-19: '
            '레지던트 11명(보철5·치주3·보존3), 정규직 표시, 인턴 수료 조건, '
            '서류 방문접수 11/16~20 및 시험·면접 날짜를 확인함. '
            '공고 JPG3087104 원본 SHA256·육안 판독과 직무 HWP3087106 '
            '바이트 SHA256·BodyText 검증 완료. 구체 시술은 원문에 미기재. '
            '중앙보훈병원 원문 채용공고를 2026-11-20 재조회해 방문접수 '
            '11/20 17:00(KST)과 접수처 제3관 2층을 교차확인함. '
            '실제 현장 접수 가능 상태·서류제출 완료·잔여인원은 미확인.'
        ),
    },
    # Verified 2026-11-19 against official JOB-ALIO and the live EJM 12745
    # application page. UTC deadline is date-only in ALIO; do not invent KST cutoff.
    # Public portal evidence is separate from newly SHA-verified original job-duty PDF.
    'a305734': {
        'reader_scope': '공식 접수 페이지에서 박사학위 요건·추천서 3건·UTC 마감 표기를 확인했습니다. 현재 남은 인원이나 최종 제출 성공까지 확인한 것은 아닙니다.',
        'organization': '한국조세재정연구원',
        'title': '[한국조세재정연구원] 연구위원급(Research Fellow) 정기채용',
        'source_end_date': '2026-11-30',
        'expected_source_seats': '10',
        'source_employment': ['정규직'],
        'source_url': 'https://econjobmarket.org/positions/12745',
        'checked_on': '2026-11-19',
        'utc_application_window_label': '2026-10-06 ~ 2026-11-30 (UTC 기준·한국시간 종료시각 미확정)',
        'role_mix_note': (
            '한국조세재정연구원 연구위원급 정규직 전체 10명 모집입니다. '
            '경제학 또는 관련 분야 박사학위 소지자(취득 예정자 포함)이며, '
            'Econ Job Market 원문은 임용 시작 때까지 박사학위를 취득해야 한다고 안내합니다. 원활한 한국어 의사소통 능력도 요구합니다. '
            '조세·재정 및 공공부문 정책 연구를 수행하고 주근무지는 세종입니다. '
            '서류 → 면접 → 세미나 전형을 거치며, 지원서에는 영문 자기소개서(Cover letter), '
            '이력서(CV), 연구논문(Job market paper) 및 추천인 3명의 추천서 제출이 요구됩니다. '
            '추천서는 추천인이 EJM 시스템에서 제출하며 세부 업로드 절차를 확인하세요. '
            '실제 공식 EJM 공고에는 2026년 11월 23일 공개 재확인 기준 '
            '“accepting applications”로 표시됐지만 10명이 모두 남아 있다는 실시간 증거는 아닙니다. '
            '원문 접수마감은 2026년 11월 30일 midnight UTC 표기입니다. '
            'ALIO 게시 종료시각 23:59 KST를 원서마감으로 바꾸거나 '
            'midnight의 해석 없이 한국시간 마감시각을 임의 확정하지 마세요.'
        ),
        'scope': (
            '2026-11-19 공식 JOB-ALIO a305734 및 2026-11-23 Econ Job Market positions/12745 '
            '공개 HTML 직접 확인: 정규직 10명·박사(예정자 포함)·한국어 의사소통·세종·정책 연구·추천서3·'
            '접수수락 표시와 UTC 마감 표현. 제출 화면 로그인 후 최종 접수 성공까지는 '
            '검증하지 않았음. 기존 증거 ZIP 공고PDF3079032·직무PDF3079033 원본 바이트 SHA를 '
            '독립 대조했으며 직무기술서 1쪽 내용을 직접 판독함. '
            '공고 PDF의 일부 숫자는 폰트 추출 문제로 이전 육안 기록과 '
            'EJM 공식 화면으로 대조. 잔여결원·실제 제출 성공 미검증.'
        ),
    },
    # JOB-ALIO public text (2026-11-19) conflicts internally: employment is
    # labeled '정규직' while the selection-stage heading is '개방형 계약직'.
    # This is a discrepancy notice only; do not assert a confirmed contract
    # type or duration before reading each original recruitment HWP.
    'a307146': {
        'organization': '(재)우체국물류지원단',
        'title': '2027년도 우체국물류지원단 1분기 정기채용(개방형직위_인천국제물류사업소장) 공고',
        'source_end_date': '2026-12-01',
        'expected_source_seats': '1',
        'source_employment': ['정규직'],
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=307146',
        'checked_on': '2026-11-19',
        'role_mix_note': (
            '공식 JOB-ALIO의 고용형태 표에는 정규직 1명이라고 표시되지만 '
            '같은 공식 페이지의 전형단계별 채용정보는 개방형 계약직으로 명시합니다. '
            '따라서 정규직 1명으로만 단정하거나 계약기간을 추정하지 마세요. '
            '인천국제물류사업소장 직위이며, 지원자는 7급 이상 국가·지방공무원 1년 이상, '
            '물류·운송 분야 민간경력 15년 이상, 또는 기관 내부 4급 사무직이나 '
            '10년 이상 기술급 등 공고의 대안 경력조건을 확인해야 합니다. '
            '원서접수 개시·마감시각 및 정확한 고용계약 조건은 공식 첨부 HWP와 기관 지원창에서 확인 필요입니다.'
        ),
        'scope': 'JOB-ALIO a307146 공개 HTML의 정규직 분류·개방형 계약직 전형명 충돌, 1명·사업소장 경력요건·게시 종료일 확인. 공고 HWP 원본 바이트/SHA, 계약기간 및 실제 접수시간은 아직 검증하지 않았으며 직무원본 검토수에 합산하지 않음.',
    },
    'a307147': {
        'organization': '(재)우체국물류지원단',
        'title': '2027년도 우체국물류지원단 1분기 정기채용(개방형직위_안동사업소장) 공고',
        'source_end_date': '2026-12-01',
        'expected_source_seats': '1',
        'source_employment': ['정규직'],
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=307147',
        'checked_on': '2026-11-19',
        'role_mix_note': (
            '공식 JOB-ALIO의 고용형태 표에는 정규직 1명이라고 표시되지만 '
            '같은 공식 페이지의 전형단계별 채용정보는 개방형 계약직으로 명시합니다. '
            '따라서 정규직 1명으로만 단정하거나 계약기간을 추정하지 마세요. '
            '안동사업소장 직위이며, 지원자는 7급 이상 국가·지방공무원 1년 이상, '
            '물류·운송 분야 민간경력 15년 이상, 또는 기관 내부 4급 사무직이나 '
            '10년 이상 기술급 등 공고의 대안 경력조건을 확인해야 합니다. '
            '원서접수 개시·마감시각 및 정확한 고용계약 조건은 공식 첨부 HWP와 기관 지원창에서 확인 필요입니다.'
        ),
        'scope': 'JOB-ALIO a307147 공개 HTML의 정규직 분류·개방형 계약직 전형명 충돌, 1명·사업소장 경력요건·게시 종료일 확인. 공고 HWP 원본 바이트/SHA, 계약기간 및 실제 접수시간은 아직 검증하지 않았으며 직무원본 검토수에 합산하지 않음.',
    },
    # 2026-11-19: official PNUH notice PDF 3088502 p1/p3, plus three
    # job-description PDFs from ZIP 3088504 checked with binary SHA256.
    # All 33 seats belong to one notice; this is NOT 33 remaining live openings.
    'a307225': {
        'reader_scope': '공식 모집표의 직종별 인원·지원조건과 접수일정을 확인했습니다. 방사선사 직무자료의 분류 표기 불일치는 기관 확인이 필요합니다.',
        'organization': '부산대학교병원',
        'title': '2026년도 일반직(간호, 행정, 보건직) 신규직원 블라인드 공개채용 모집 공고',
        'source_end_date': '2026-12-03',
        'expected_source_seats': '33',
        'source_employment': ['정규직'],
        'application_start': '2026-11-19',
        'application_end_date': '2026-12-03',
        'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3088502',
        'notice_source_sha256': 'a45a7bebec1929e6f18315ee8ace0aa20b59ddf6af5cb40503d206f46faa3cd2',
        'checked_on': '2026-11-19',
        'hiring_breakdown': (
            '진료지원간호사 30명 · 의료사회복지사 2명 · '
            '산부인과 초음파실 방사선사 1명 = 정규직 총33명'
        ),
        'role_mix_note': (
            '부산대학교병원 공식 8쪽 공고문 1쪽 모집표에서 간호직30명, '
            '행정직 의료사회복지사2명, 보건직 산부인과 방사선사1명을 확인했습니다. '
            '간호직은 간호사면허, 병원·종합병원·군병원 임상경력3년 이상과 '
            '야간·교대근무 가능 요건(요양병원 경력 제외)이 적용됩니다. '
            '행정직은 의료사회복지사 자격증과 영어성적(예: TOEIC700), '
            '보건직은 방사선사면허와 영어성적(예: TOEIC600) 등 '
            '각 직종별 상이한 요건을 확인해야 합니다. '
            '지원서 접수는 2026년11월19일~12월3일17시(KST)까지입니다. '
            'ALIO 게시 마감23:59와 혼동하지 마세요. '
            '이 33명은 공고 전체 모집정원이며 실시간 잔여인원 확인치가 아닙니다. '
            '방사선사 직무PDF 일부 분류칸의 심장초음파 표기와 달리 '
            '모집분야·직무 제목·주요 수행업무는 산부인과 초음파이므로 '
            '세부 진료배치를 임의 추정하지 않습니다.'
        ),
        'scope': (
            '공식 ALIO a307225 HTML과 공고PDF 3088502(263129 bytes, '
            'SHA256 a45a7bebec1929e6f18315ee8ace0aa20b59ddf6af5cb40503d206f46faa3cd2) '
            '1·3쪽 모집표·일정 원문 육안 대조. '
            '직무 ZIP3088504(243748 bytes, SHA256 '
            '5919b21c2acdd40383a34da232ab3808cc6b0ca01e904a2cb5b26dce8fca10cf) '
            '내 간호·의료사회복지·산부인과 방사선사 직무PDF 각1쪽 판독. '
            '12/3 17시 접수마감 공식 공고 확인; 현재 잔여 결원·지원 제출 성공 미검증.'
        ),
    },
    # Official a307251 HTML 2026-11-19: source-only note, NOT a duty-original audit.
    # Nine earlier pharmacist notices coexist; independent vacancies are unproven.
    'a307251': {
        'organization': '경상국립대학교병원',
        'title': '[창원경상국립대학교병원] 약무직 채용공고',
        'source_end_date': '2026-12-31',
        'expected_source_seats': '5',
        'source_employment': ['정규직'],
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=307251',
        'checked_on': '2026-11-19',
        # Nine overlapping notices + unverified portal reception are not proof
        # of five independently open vacancies. Keep the explanatory detail
        # accessible, but do not present it as a verified current opening.
        'application_status_unconfirmed': True,
        'role_mix_note': (
            '2026년 11월 19일 등록된 창원경상국립대학교병원 약무직 공고의 '
            '정규직 채용예정 인원은 5명입니다. 공식 JOB-ALIO 응시자격은 '
            '약사 면허증 소지자 또는 2027년 면허 취득예정자이며, '
            '접수 마감일 현재 만 20세 이상 60세 미만과 병역 관련 조건을 '
            '확인해야 합니다. 동일 기관에 약무직 유사 공고가 여러 건 이전부터 '
            '게시되어 있으나 서로 독립된 추가 채용인지, '
            '변경·후속공고인지 공식 원본 대조가 끝나지 않았습니다. '
            '따라서 이전 공고의 예정인원과 5명을 임의로 합산하거나 '
            '현재 남은 결원이 5명이라고 단정하지 마세요. '
            '2026년 12월 31일은 ALIO 게시 종료일이며 '
            '실제 원서접수 마감시각·기관 채용포털의 접수 활성 여부는 '
            '별도 공식 확인이 필요합니다.'
        ),
        'scope': (
            '2026-11-19 JOB-ALIO a307251 공식 HTML에서 정규직 약무직 5명, '
            '약사 면허 또는 2027년 취득예정, 만 20~59세 지원 조건과 '
            '게시기간 11/19~12/31을 확인. ALIO 원본 수집 1176건에서 '
            '동일 기관의 과거 약무직 유사 게시 9건(a294598, a294624, '
            'a297599, a298427, a303321, a305304, a292472, a299412, '
            'a306275)을 확인했으나 공식 첨부 원본 비교를 통해 '
            '중복/변경/별도 채용을 확정하지 않았음. '
            '새 공고 첨부 PDF3088867·PDF3088868·HWP3088879의 '
            '바이너리 SHA·세부 직무를 독립 판독하지 않았으므로 '
            '직무 원본 검증 누적 건수에는 포함하지 않음. '
            '접수 가능 여부와 잔여 결원도 별도 확인 필요.'
        ),
    },
    # Official JOB-ALIO public HTML rechecked 2026-11-18. These new
    # postings are not separately audited HWP/PDF job-duty originals.
    'a306990': {
        'organization': '국방과학연구소',
        'title': "국방과학연구소 '27년 상반기 임용 공개채용",
        'source_end_date': '2026-12-02',
        'expected_source_seats': '162',
        'source_employment': ['무기계약직', '정규직', '계약직'],
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=306990',
        'checked_on': '2026-11-18',
        'role_mix_note': (
            '공식 JOB-ALIO의 162명은 정규직·무기계약직·비정규직을 합친 공고 전체 인원입니다. '
            '정규직 162명 모집으로 해석할 수 없으며 각 응시코드별 고용형태·모집인원은 '
            '기관 공고문의 모집분야 첨부에서 따로 확인해야 합니다. '
            '2027년 3월 16일부터 근무 가능해야 하며, 연구직·기술직·관리직 정규직 지원자는 '
            '분야별 공인영어성적 요건(예: TOEIC 700점 또는 이에 상응하는 시험)을 확인하세요. '
            '기술기사직·행정직 정규직, 기능원 무기계약직 등은 영어 제출 대상이 서로 다릅니다. '
            '12월 2일은 ALIO 게시 종료일이며 실제 접수 마감시각은 기관 지원화면에서 별도 확인하세요.'
        ),
        'scope': 'JOB-ALIO 306990 공개 HTML의 정규직·무기계약직·비정규직 혼합, 공고상 162명, 자격별 영어 제출대상과 임용예정일 확인. 각 고용형태/응시코드별 선발인원, HWP 모집분야 원본 SHA, 실제 접수시각·포털 활성은 미검증. 직무원본 검토건수에 합산하지 않음.',
    },
    'a307189': {
        'organization': '한국도로공사',
        'title': '2026년 한국도로공사 전문연구원(AI·데이터분석) 채용 공고',
        'source_end_date': '2026-12-02',
        'expected_source_seats': '4',
        'source_employment': ['무기계약직'],
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=307189',
        'checked_on': '2026-11-18',
        'role_mix_note': (
            '공식 JOB-ALIO 분류는 정규직이 아닌 무기계약직 전문연구원 4명입니다. '
            '지원자는 관련 전공 박사학위, 관련 전공 석사 취득 후 해당분야 3년 이상 경력, '
            '또는 관련 전공 학사 취득 후 해당분야 6년 이상 경력 중 하나를 충족해야 합니다. '
            '해당분야는 AI·데이터 분석 및 모델 설계·구현 등이며, '
            '2027년 1월 중 인턴 근무 시작부터 경북 본사 근무가 가능해야 합니다. '
            '12월 2일은 ALIO 게시 종료일로, 실제 접수마감 시각은 기관 공고에서 확인이 필요합니다.'
        ),
        'scope': 'JOB-ALIO 307189 공개 HTML의 무기계약직 4명과 학위·경력 대안요건, AI 데이터 직무, 2027년 1월 경북 본사 인턴 시작 확인. 별도 PDF 직무원본과 실제 접수 시각은 미검증.',
    },
    # New 2026-11-18 ALIO notice and employer HTML #790549, not a verified
    # HWP/HWPX job-description file. This is a fixed-term leadership appointment
    # despite the ALIO feed label "정규직". Never imply an indefinite tenure.
    'a307171': {
        'organization': '학교법인한국폴리텍',
        'title': '한국폴리텍대학 지역대학장(서울강서, 화성, 충주, 울산) 공개초빙 공고',
        'source_end_date': '2026-11-25',
        'expected_source_seats': '4',
        'source_employment': ['정규직'],
        'source_url': 'https://www.kopo.ac.kr/board.do?menu=10523&mode=view&post=790549',
        'checked_on': '2026-11-18',
        'application_start': '2026-11-18',
        'application_end_date': '2026-11-25',
        'role_mix_note': (
            'ALIO에는 정규직 4명으로 등록되어 있지만 지역대학장 직위의 임기는 2년입니다. '
            '서울강서·화성·충주·울산캠퍼스 중복지원은 불가합니다. '
            '기관은 등기우편 또는 평일 방문접수를 받으며 2026년 11월 25일 18:00까지 '
            '접수처에 도착한 서류만 유효하다고 안내합니다. '
            '우편 접수자는 정상 접수 여부를 담당자에게 확인해야 합니다. '
            'ALIO 게시 종료일의 23:59를 원서접수 마감시각으로 해석하지 마세요.'
        ),
        'scope': 'ALIO a307171 공개 HTML에서 정규직4명·응시자격 및 2년 임기 확인. 기관 공식 게시물 790549에서 중복지원 금지, 방문/등기우편, 11월25일18:00 도착 마감 교차 확인. 첨부 HWP/HWPX 본문·바이트 SHA 및 현재 접수실화면은 이 검증 범위 밖.',
    },
    # Official ALIO HTML reviewed 2026-11-18. These do NOT count as newly
    # extracted PDF/HWP duties; the snapshots and field counts remain intact.
    'a306665': {
        'organization': '충북대학교병원',
        'title': '2026년도 제6차 충북대학교병원 신규직원 블라인드 채용 공고',
        'source_end_date': '2026-11-18',
        'expected_source_seats': '13',
        'source_employment': ['정규직'],
        'source_url': 'https://cbnuh.recruiter.co.kr/app/jobnotice/view?jobnoticeSn=270620&systemKindCode=MRS2',
        'checked_on': '2026-11-18',
        'application_start': '2026-11-04T00:00:00+09:00',
        'application_end_date': '2026-11-18',
        'role_mix_note': (
            '기관 공식 채용페이지에서 확인한 실제 원서접수 마감은 2026년 11월 18일 12:00입니다. '
            'ALIO 게시 종료일(11월 18일)을 23:59 원서접수 마감으로 해석하면 안 됩니다. '
            '공고 전체 모집인원 13명은 행정직(행정·회계), 의료기술직(방사선사), '
            '원무직(조리원), 환경관리직(미화원), 시설관리직(기계) 모집분야의 합계입니다. '
            '분야별 정확한 인원과 필수 면허·자격은 첨부 공고문을 확인하세요.'
        ),
        'scope': 'CBNUH 공식 채용포털 HTML에서 2026-11-04 00:00~11-18 12:00 실제 접수기간 확인. JOB-ALIO 공개 HTML은 정규직 총13명 및 6개 분야 확인. 첨부 PDF/ZIP 바이트와 분야별 인원·면허 원문은 이번에 검증하지 않았음.',
    },
    'a306660': {
        'organization': '한국보훈복지의료공단',
        'title': '[원주보훈요양원] 2026년 제7차 요양보호직 공개채용',
        'source_end_date': '2026-11-18',
        'expected_source_seats': '12',
        'source_employment': ['정규직'],
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=306660',
        'checked_on': '2026-11-18',
        'application_start': '2026-11-03',
        'application_end_date': '2026-11-18',
        'role_mix_note': (
            '요양보호직 12명 공고 중 2026년 12월 1일 즉시 임용 예정은 8명입니다. '
            '12명 전원을 즉시 근무할 결원으로 계산하지 마세요. '
            '요양보호사 자격증(합격증은 임용 전 자격증 제출)과 3교대 근무 가능 여부가 필수이며, '
            '원서접수 방법은 우편·방문·이메일입니다.'
        ),
        'scope': 'ALIO 공식 공개 HTML: 11월3일~18일17시 원서접수, 총12명/12월1일 즉시임용 8명, 요양보호사 자격 및 3교대 조건. 첨부 PDF/HWP 바이트 검증 건수에 넣지 않음.',
    },
    'a306718': {
        'organization': '한국보훈복지의료공단',
        'title': '[광주보훈병원] 정규직 보건직 5급(임상병리사), 기능직(간호조무사, 시설_전기) 직원 채용 공고',
        'source_end_date': '2026-11-18',
        'expected_source_seats': '6',
        'source_employment': ['정규직'],
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=306718',
        'checked_on': '2026-11-18',
        'application_start': '2026-11-04',
        'application_end_date': '2026-11-18',
        'role_mix_note': (
            '기관 공식 ALIO의 지원서 접수 마감은 2026년 11월 18일 10:00입니다. '
            '전체 6명은 임상병리사 2명, 간호조무사 3명, 시설 전기 1명의 합계이며 '
            '동일 분야 6명 모집이 아닙니다. 임상병리사는 면허증, 간호조무사는 자격증과 '
            '교대 또는 상근근무 가능, 시설 전기는 전기산업기사 또는 전기공사산업기사 '
            '이상 자격이 필요합니다. 게시 종료일 23:59를 지원 마감으로 쓰지 마세요.'
        ),
        'scope': 'JOB-ALIO 306718의 공개 채용 절차와 자격·분야별 2+3+1을 직접 확인함. 원본 PDF/HWP 첨부 바이트·SHA 및 세부 직무 원본 검증으로 집계하지 않음.',
    },
    'a307074': {
        'organization': '분당서울대학교병원',
        'title': '분당서울대학교병원 경력(간호직, 보건직), 신입(보건직) 직원 채용공고',
        'source_end_date': '2026-11-26',
        'expected_source_seats': '14',
        'source_employment': ['정규직'],
        # The feed's single 정규직 label includes 6 general-position interns.
        # Keep the notice searchable, but do not put 14 seats in the regular-only review queue.
        'regular_review_hold_due_to_mixed_role_units': True,
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=307074',
        'checked_on': '2026-11-18',
        'hiring_breakdown': (
            '경력 간호직 6명(영상의학과5·핵의학과1), 경력 보건직 2명(핵의학과), '
            '신입 일반직인턴(보건직) 6명(진단검사의학과3·핵의학과2·신경외과1), 합계14명'
        ),
        'role_mix_note': (
            'ALIO의 전체 고용형태는 정규직이지만 신입 6명은 공고 내 일반직인턴(보건직) '
            '모집단위입니다. 전체14명을 즉시 확정 일반직 정규직 인원으로 단정하지 마세요. '
            '경력직은 분야별 면허·종합병원 경력요건이 다르고 신입은 분야별 면허 및 '
            '공인어학성적(TOEIC750·TOEIC Speaking IM3·NEW TEPS285 중 1개 이상)이 필수입니다. '
            '기관의 경력직 8명 전용 채용공고는 2026-11-17 12:00~11-26 23:59 접수로 확인됐습니다. '
            '이 시각은 경력 간호직 6명·보건직 2명에만 해당합니다. '
            '신입 일반직인턴(보건직) 6명의 기관별 실제 접수화면·마감시각은 별도 확인이 필요합니다. '
            '경력직 확인 시각을 전체 14명 공통 접수마감으로 사용하지 마세요.'
        ),
        'scope': 'ALIO 공식 공개 HTML의 여섯 세부분야 5+1+2+3+2+1=14명과 필수 면허/경력/영어요건. 기관 경력직원 별도 접수페이지 https://snubh.recruiter.co.kr/app/jobnotice/view?jobnoticeSn=272568&systemKindCode=MRS2 에서 경력8명 11월17일12시~26일23:59 확인. 신입6명 접수화면과 원본 첨부 직무검토는 확인하지 않음.',
    },
    # ALIO official detail HTML, 2026-11-18: "상시모집" describes the posting,
    # not verified remaining vacancies or an independently live application portal.
    'a305089': {
        'organization': '충남대학교병원',
        'title': '2026년 하반기 신규의료진(임상교수요원) 공개채용 모집공고(상시모집)',
        'source_end_date': '2026-12-31',
        'expected_source_seats': '14',
        'source_employment': ['정규직'],
        'source_url': 'https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=305089',
        'checked_on': '2026-11-18',
        'application_status_unconfirmed': True,
        'role_mix_note': (
            'ALIO에는 임상교수요원 정규직 총 14명 및 상시모집으로 등록되어 있습니다. '
            '이 숫자는 현재 남아 있는 확정 결원 14명이라는 뜻이 아닙니다. '
            '실제 접수 가능 여부·분야별 잔여 인원은 기관 채용시스템에서 별도 확인해야 합니다. '
            '지원자는 경력요건 중 하나와 연구실적요건 중 하나를 각각 충족해야 합니다. '
            '연구실적은 원칙적으로 최근 3년 이내이며 학위논문은 기간 제한 없음; 경력기준 예외 인정은 기관 심의 사항입니다.'
        ),
        'scope': 'ALIO 공식 HTML의 정규직 의사직 14명·상시모집 표기, 경력 및 연구실적 요건 확인. 기관 접수창의 실시간 활성·잔여 결원 및 PDF 직무원본 바이트는 미검증; 현재 접수 가능 확정 또는 직무원본 검증 건수로 계산하지 않음.',
    },
    # ALIO official HTML rechecked 2026-11-18: published count is not
    # independently confirmed current vacancies for this long-running notice.
    'a292002': {
        'organization': '경상국립대학교병원',
        'title': '권역외상센터 진료전담교수 채용공고',
        'source_end_date': '2026-12-31',
        'expected_source_seats': '14',
        'source_employment': ['정규직'],
        'source_url': 'https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=292002',
        'checked_on': '2026-11-18',
        'application_status_unconfirmed': True,
        'role_mix_note': (
            'JOB-ALIO에 정규직 진료전담교수 14명으로 등록된 공고입니다. '
            '2025년 10월 17일~2026년 12월 31일은 ALIO 공고 게시기간이며 '
            '현재 잔여 채용인원 14명으로 확정할 수 없습니다. '
            '지원서 접수창의 현재 활성 상태와 실제 잔여 결원은 기관 채용시스템에서 별도 확인해야 합니다. '
            '공식 ALIO 응시자격에는 교육 및 연구경력 통산 4년 이상 등이 명시되어 있습니다. '
            '게시 종료일을 임의의 원서접수 마감시각으로 바꾸지 마세요.'
        ),
        'scope': 'JOB-ALIO 공식 HTML에서 정규직 14명·게시기간 2025-10-17~2026-12-31·경력 요건 확인. 기관 실제 접수창 활성, 잔여 인원, 원본 PDF/HWP SHA, 별도 최신 공고와의 독립 모집 여부는 미확인; 현재 접수 가능한 정규직 모집 수나 직무원본 검증 건수에 포함하지 않음.',
    },
    'a306875': {
        'organization': '분당서울대학교병원',
        'title': '분당서울대학교병원 신입(업무지원직) 직원 채용 공고',
        'source_end_date': '2026-11-20',
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=306875',
        'checked_on': '2026-11-18',
        'application_start': '2026-11-11',
        'application_end_date': '2026-11-20',
        'notice_source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3086118',
        'notice_source_sha256': '673c2e9f3ba930f5c4d69b9bcf1a7410f44818ae26228059f4ef84f81f9f2e82',
        'qualification_sha256': '2024e16e7fce0db8cdc3a5633b17fa8200d330a899d7736e00468b3f8c521331',
        'reported_total': '66',
        'field_requirements': [
            ('외래', 3, '의료기관 또는 기업체·기관·단체 근무경험 6개월 이상'),
            ('병동', 50, '의료기관 또는 기업체·기관·단체 근무경험 6개월 이상'),
            ('린넨·멸균·세척·수선', 5, '의료기관 또는 기업체·기관·단체 근무경험 6개월 이상'),
            ('주차·보안·환자이송·물류창고·배송·약품배송·관리', 2, '의료기관 또는 기업체·기관·단체 근무경험 6개월 이상'),
            ('시설유지보수(목마공)', 1, '의료기관 또는 기업체·기관·단체 근무경험 6개월 이상'),
            ('시설유지보수(기계)', 4, '온수온돌·공조냉동기계·자동화설비·용접 분야·위험물·가스·에너지관리 기능사 중 1개 이상. 해당 상위 자격도 인정'),
            ('시설유지보수(환경처리)', 1, '환경기능사 또는 수질환경산업기사 이상 중 1개 이상'),
        ],
        'scope': '공개 ALIO 지원자격과 공고문 PDF 1쪽의 분야별 인원·필수요건, PDF 3쪽의 접수 날짜 대조. 정확한 마감시각은 공고문에 미기재. 기존 외래 직무 검증 범위는 유지.',
    },
    # Original PDFs already reviewed in VERIFIED_DUTIES (39-record count unchanged).
    # These independent employer notices corroborate the actual reception clocks.
    'a306662': {
        'organization': '한국원자력의학원',
        'title': '2027년 한국원자력의학원 신규간호사 공개채용 공고',
        'source_end_date': '2026-11-18',
        'application_start': '2026-11-03',
        'source_url': 'https://kcch.re.kr/rirams/board/generalBoardView7.do?no=23098',
        'checked_on': '2026-11-17',
        'scope': 'Employer recruitment notice 2026-40: nursing 50 places and online reception through 2026-11-18 17:00 KST; official HTML is separate from already verified ALIO PDF',
    },
    'a306799': {
        'organization': '국립중앙의료원',
        'title': '2027년 신규간호사(간호직 6급, 간호부) 채용 공고',
        'source_end_date': '2026-11-23',
        'application_start': '2026-11-06',
        'source_url': 'https://www.nmc.or.kr/nmc/board/B0000007/28373',
        'checked_on': '2026-11-17',
        'scope': 'Employer recruitment notice 2026-436: online reception through 2026-11-23 10:00 KST; 97 positions and pool nature originate from existing ALIO PDF review',
    },
    'a306755': {
        'organization': '한국원자력의학원',
        'title': '제2026-5회 한국원자력의학원 정기직원채용',
        'source_end_date': '2026-11-20',
        'application_start': '2026-11-05',
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=306755',
        'checked_on': '2026-11-17',
        'scope': 'ALIO official detailed text: application window and 17:00 cutoff; no attachment-byte or field-by-field headcount verification',
    },
    'a306925': {
        'organization': '서울대학교치과병원',
        'title': '2027년도 치과의사전공의(인턴) 모집 공고',
        'source_end_date': '2027-01-22',
        'application_start': '2027-01-18T09:00:00+09:00',
        'source_url': 'https://www.snudh.org/portal/blindEmpmn/view.do?menuNo=29060340&empSeq=6676',
        'checked_on': '2026-11-17',
        'scope': 'Employer official HTML: in-person/postal reception starts 2027-01-18 09:00 and ends 2027-01-22 18:00; not ALIO publication start or a new job-duty original',
        # SNUDH employer notice HTML 2026-11-11 says 2027 for expected dentist licensure,
        # whereas the ALIO a306925 public qualification still says 2026.
        # Keep collected originals unchanged and show the discrepancy only if
        # the exact old phrase is still present in this notice's detail.
        'qualification_year_discrepancy': {
            'expected_alio_fragment': '2026년도 취득예정자',
            'notice': ('ALIO 응시자격에는 2026년도 취득예정자로 표시되지만, '
                       '서울대학교치과병원 공식 2027년도 인턴 모집공고에는 '
                       '2027년도 취득예정자로 표시됩니다. 지원 전 기관 원문을 확인하세요.'),
        },
    },
    'a306942': {
        'organization': '전남대학교병원',
        'title': '2027년도 치과의사전공의(인턴) 모집 공고',
        'source_end_date': '2027-01-22',
        'application_start': '2027-01-18T09:00:00+09:00',
        'source_url': 'https://cnuh.recruiter.co.kr/app/jobnotice/view?systemKindCode=MRS2&jobnoticeSn=271734',
        'checked_on': '2026-11-17',
        'scope': 'Employer official 2027 internship recruitment portal: online application 2027-01-18 09:00 to 2027-01-22 17:00 KST; distinct from ALIO publication and existing 2024 curriculum-only HWP proof',
    },
    'a306913': {
        'organization': '한국해양과학기술원',
        'title': '[제27-01-01호 및 제27-02-01호]한국해양과학기술원 2027년 1차 직원(정규직/무기계약직) 채용',
        'source_end_date': '2026-11-26',
        'application_start': '2026-11-13',
        'source_url': 'https://www.gojobs.go.kr/apmView.do?empmnsn=308183',
        'checked_on': '2026-11-17',
        'hiring_breakdown': '정규직 9명 · 무기계약직 14명 (합계 23명)',
        'scope': 'Nara Iltter official notice 308183: application dates 2026-11-13 to 11-26 10:00 KST and employment types 9+14; not attachment/PDF byte validation or duties verification',
    },
    # Official NPS PDF now confirms each track's one contract position and
    # the exact cutoff. Keep the conflicting ALIO classification unchanged.
    'a306988': {
        'organization': '국민연금공단',
        'title': '2026년 제1차 국민연금공단 준법감시담당자(기금운용직) 채용공고',
        'source_end_date': '2026-12-01',
        'application_start': '2026-11-17',
        'application_end_date': '2026-12-01',
        'source_employment': ['정규직'],
        'confirmed_employment': '계약직',
        'employment_note': 'ALIO는 정규직으로 분류하지만 공식 공고문은 두 분야 각1명의 계약직, 계약기간3~5년으로 명시합니다. 원문 계약조건을 확인하세요.',
        'source_url': 'https://www.alio.go.kr/download/download.json?fileNo=3087074',
        'checked_on': '2026-11-18',
        'scope': '공식 공고PDF1쪽에서 분야별 각1명·계약직3~5년, 5항에서12월1일18시 마감을 확인. ALIO 정규직 분류와 공고문이 다름. 직무PDF는 별도 확인.',
    },
    # Official JOB-ALIO a307149 details, read 2026-11-17: the announcement
    # appears 11/17, but applications do NOT begin until 11/24. Neither
    # opening clock nor closing clock was confirmed: preserve date-only.
    'a307149': {
        'organization': '한국동서발전(주)',
        'title': '한국동서발전(주) 2027년 상반기 신입직원(대졸수준(일반/보훈) 및 고졸) 선발',
        'source_end_date': '2026-12-01',
        'expected_source_seats': '101',
        'source_employment': ['정규직'],
        'application_start': '2026-11-24',
        'application_end_date': '2026-12-01',
        'source_url': 'https://job.alio.go.kr/recruitview.do?idx=307149',
        'checked_on': '2026-11-19',
        'role_mix_note': (
            '공식 JOB-ALIO의 101명은 대졸수준 일반전형, 대졸수준 보훈전형과 '
            '고졸 일반전형을 합친 공고 전체 인원입니다. 개별 직무별 인원은 '
            '이 공개 HTML만으로 확정하지 않습니다. '
            '대졸수준 일반전형은 원칙적으로 TOEIC 700점 이상이 필요하지만 '
            '보훈대상자·장애인·전문자격증 소지자에게는 공식 예외가 있습니다. '
            '대졸수준 보훈전형은 별도의 어학 제한이 없고, '
            '고졸 일반전형은 최종학력 기준을 확인해야 하며 전문대·대학교 '
            '졸업자 및 졸업예정자는 지원할 수 없습니다. '
            '원서접수는 11월 24일~12월 1일 예정이나 실제 개시·마감시각은 '
            '확인되지 않았습니다. '
            '또한 JOB-ALIO 일정표에는 입사일이 2026년 3월 15일로 표기되어 '
            '2027년 상반기 채용 일정과 연도가 충돌하므로 기관 정정공고를 '
            '확인해야 하며 2027년으로 임의 보정하지 않습니다.'
        ),
        'scope': '2026-11-19 JOB-ALIO a307149 HTML 직접 재확인: 전체 정규직 101명, 대졸 일반/보훈·고졸 일반 자격 및 어학 예외, 11/24~12/01 날짜만 확인, 입사일 연도 충돌. 직무별 인원·공식 PDF/ZIP 원본 SHA 및 실제 시작/종료시각 미검증.',
    },
}


DETAIL_LABELS = {
    'recrutSeNm': '채용 구분',
    'aplyQlfcCn': '지원 자격',
    'disqlfcRsn': '결격사유',
    'scrnprcdrMthdExpln': '전형 절차',
    'prefCn': '우대사항',
    'prefCondCn': '우대조건',
    'jobDscrptn': '직무 설명 (공식 상세자료)',
}


def clean(value):
    if isinstance(value, list):
        return ', '.join(map(str, value))
    return str(value or '').strip()


def count_label(value):
    # Reused from detail-integrity Draft PR #12; never sum ambiguous fields.
    raw = '' if value is None else str(value).strip()
    return raw + '명' if re.fullmatch(r'[0-9]+', raw) else raw or '미기재 · 공식 공고 확인'


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
            <= datetime.now(timezone.utc)
        )
    except ValueError:
        return False


def render(post, detail, related_posts=(), notice_review=None):
    review = notice_review or {}
    if review.get("fingerprint") != notice_fingerprint(post, detail):
        review = {}
    duplicate_id = review.get("representative_id") if review.get("decision") == "same_notice" else None
    duplicate = bool(duplicate_id and duplicate_id != post.get("id"))
    review_html = ""
    if review and review.get("publish_note", True):
        peer_links = " · ".join(f'<a href="{peer}.html">{peer} 공고 비교</a>' for peer in review["peer_ids"] if peer != post.get("id"))
        proof_links = " · ".join(f'<a href="{escape(src["url"], quote=True)}" rel="noopener noreferrer">공식 {label} 원본</a>' for label, src in zip(("공고문", "직무기술서"), review["sources"]))
        review_html = ('<section id="notice-review" aria-label="유사 공고 구분 안내"><h2>유사 공고 구분 안내</h2>'
            + f'<p>{escape(review["public_note"])}</p><p>{peer_links}</p>'
            + (f'<p><a href="{duplicate_id}.html">동일 채용의 대표 공고 보기</a></p>' if duplicate else "")
            + f'<p>{proof_links} · 최종 확인일: {escape(review["checked_on"])}</p></section>')
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

    verified_application_notice = VERIFIED_APPLICATION_NOTICES.get(pid, {})
    if (verified_application_notice and (post.get('alio') is not True
            or verified_application_notice['organization'] != org
            or verified_application_notice['title'] != title
            or verified_application_notice['source_end_date'] != clean(post.get('due'))[:10]
            or (verified_application_notice.get('source_employment')
                and verified_application_notice['source_employment'] != post.get('emp'))
            or (verified_application_notice.get('expected_source_seats') is not None
                and verified_application_notice['expected_source_seats'] != clean(post.get('n'))))):
        verified_application_notice = {}
    verified_duties = VERIFIED_DUTIES.get(pid, {})
    # Bind editorial evidence to the exact notice, organization and title.
    # A reused ID or changed notice must be reviewed again before reuse.
    if (verified_duties.get('organization') != org
            or verified_duties.get('title') != title
            or (verified_duties.get('strict_source_identity') is True
                and (post.get('alio') is not True
                     or verified_duties.get('source_end_date') != clean(post.get('due'))[:10]
                     or (verified_duties.get('source_employment')
                         and verified_duties['source_employment'] != post.get('emp'))
                     or (verified_duties.get('expected_source_seats') is not None
                         and verified_duties['expected_source_seats'] != clean(post.get('n')))))):
        verified_duties = {}

    # Exact-source display correction only: preserve collection snapshots and
    # reject changed source text, identity mismatches and unsupported fields.
    for field, correction in verified_duties.get('detail_display_corrections', {}).items():
        if (field in ('aplyQlfcCn', 'disqlfcRsn') and isinstance(correction, dict)
                and isinstance(correction.get('value'), str)
                and isinstance(correction.get('expected'), str)
                and detail.get(field) == correction.get('expected')):
            detail = dict(detail, **{field: correction['value']})

    canonical = f'{BASE}/jobs/{quote(duplicate_id or pid, safe="")}.html'
    due = clean(post.get('due'))
    due_display = date_label(due, post.get('dueHasTime') is True)
    # Employer-confirmed cutoff is editorial metadata, not an ALIO feed override.
    application_cutoff = CONFIRMED_APPLICATION_CUTOFFS.get(pid, '')
    if VERIFIED_DUTIES.get(pid, {}).get('strict_source_identity') is True and not verified_duties:
        application_cutoff = ''
    if pid in VERIFIED_APPLICATION_NOTICES and not verified_application_notice:
        application_cutoff = ''
    confirmed_cutoff = application_cutoff[:16].replace('T', ' ') + ' (KST)' if application_cutoff else ''
    deadline = parse_date(due, end_of_day=True)
    # A verified application cutoff takes precedence over the publication end
    # date. Keep the feed intact and preserve the archived URL/bookmarks.
    closed = is_closed(application_cutoff or due)
    # An identity-verified long-running notice is not proof of a live vacancy.
    # Retain the accessible detail page, but do not index unconfirmed openings.
    robots_noindex = closed or verified_application_notice.get('application_status_unconfirmed') is True

    official = (
        safe_url(post.get('src'))
        or safe_url(post.get('url'))
    )
    # 기관 원문이 일시적으로 열리지 않을 때 ALIO 원본을 대체 확인 경로로 제공합니다.
    alio_reference = safe_url(post.get('url'))
    if alio_reference == official:
        alio_reference = ''
    # 허용 가능한 HTTPS 링크라는 뜻이지, 링크 응답이나 접수 가능성을 실시간 검증한 것은 아닙니다.

    verified_start = verified_duties.get('application_start', '') or verified_application_notice.get('application_start', '')
    parsed_start = parse_date(verified_start)
    verified_end = verified_duties.get('application_end_date', '') or verified_application_notice.get('application_end_date', '')
    date_end = parse_date(verified_end, end_of_day=True) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', verified_end) else None
    period_end = parse_date(application_cutoff) if application_cutoff else date_end
    source_end = verified_duties.get('source_end_date', verified_application_notice.get('source_end_date', application_cutoff[:10]))
    if (not parsed_start or not period_end or parsed_start > period_end
            or source_end != due[:10]):
        verified_start = ''
    end_label = confirmed_cutoff or (verified_end + ' (마감시각 공식 공고 확인 필요)' if date_end else '')
    confirmed_period = (date_label(verified_start, 'T' in verified_start) + ' ~ ' + end_label) if verified_start else ''

    display_employment = clean(post.get('emp'))
    if verified_application_notice.get('confirmed_employment'):
        display_employment = verified_application_notice['confirmed_employment'] + ' · ALIO 분류: ' + display_employment
    fields = [
        ('기관명', org),
        (
            '수집 모집인원 · 공식 첨부와 불일치' if verified_application_notice.get('source_headcount_conflict') else '모집인원',
            count_label(post.get('n'))
        ),
        *(([(verified_application_notice.get('hiring_breakdown_label', '기관 공식 확인 고용형태별 인원'), verified_application_notice['hiring_breakdown'])])
          if verified_application_notice.get('hiring_breakdown') else []),
        *(([('공식 원문 모집단위별 확인사항', verified_application_notice['role_mix_note'])])
          if verified_application_notice.get('role_mix_note') else []),
        ('고용형태', display_employment or '공고 확인'),
        ('학력조건', clean(post.get('edu')) or '공고 확인'),
        ('근무지역', clean(post.get('region')) or '공고 확인'),
        ('ALIO 게시 종료일 · 접수마감 원문 확인', due_display),
        ('원서 접수기간', confirmed_period or verified_application_notice.get('utc_application_window_label') or verified_application_notice.get('conditional_application_window_label') or ('접수 시작일 및 변경 여부는 공식 공고에서 확인' if confirmed_cutoff else '시작일·마감일·마감시각은 공식 첨부 공고에서 확인')),
        *(([('기관 공식 확인 접수마감', confirmed_cutoff)]) if confirmed_cutoff else []),
    ]

    # Visible discrepancy, not a rewrite: an institution's 2027 eligibility
    # wording differs from ALIO's older 2026 wording for this exact notice.
    # If the collected detail changes, do not display stale editorial evidence.
    qualification_delta = verified_application_notice.get('qualification_year_discrepancy')
    if (isinstance(qualification_delta, dict)
            and isinstance(detail.get('aplyQlfcCn'), str)
            and isinstance(qualification_delta.get('expected_alio_fragment'), str)
            and qualification_delta['expected_alio_fragment'] in detail['aplyQlfcCn']
            and isinstance(qualification_delta.get('notice'), str)):
        fields.append(('기관 공고와 ALIO 지원자격 연도 차이', qualification_delta['notice']))

    conflicts = []
    if verified_application_notice.get('confirmed_employment'):
        fields.append(('공식 공고문 고용형태', verified_application_notice['confirmed_employment']))
        conflicts.append(verified_application_notice['employment_note'])
    if post.get('n') is not None and detail.get('recrutNope') is not None and count_label(post['n']) != count_label(detail['recrutNope']):
        conflicts.append('자료 간 정보가 달라 공식 확인이 필요합니다. 모집인원: 목록 ' + count_label(post['n']) + ' / 상세 ' + count_label(detail['recrutNope']))
    for field, label in [('pbancBgngYmd', '게시 시작일'), ('pbancEndYmd', '게시 종료일')]:
        if detail.get(field):
            fields.append(('ALIO ' + label, date_label(detail[field])))
    conflict_html = ''.join('<p class="source-note">' + escape(item) + '</p>' for item in conflicts)

    rows = '\n'.join(
        f'<dt>{escape(k)}</dt><dd>{escape(v)}</dd>'
        for k, v in fields
    )

    application_review_html = ''
    if verified_application_notice:
        proof_url = safe_url(verified_application_notice.get('source_url'))
        proof_date = clean(verified_application_notice.get('checked_on'))
        field_rows = verified_application_notice.get('field_requirements', [])
        field_review = ''
        if (field_rows and str(detail.get('recrutPblntSn')) == pid.removeprefix('a')
                and str(post.get('n')) == verified_application_notice.get('reported_total')
                and isinstance(detail.get('aplyQlfcCn'), str)
                and hashlib.sha256(detail['aplyQlfcCn'].encode()).hexdigest()
                == verified_application_notice.get('qualification_sha256')):
            table_rows = ''.join(
                '<tr><th scope="row">' + escape(name) + '</th><td>' + str(count)
                + '명</td><td>' + escape(requirement) + '</td></tr>'
                for name, count, requirement in field_rows)
            field_review = (
                '<h3>같은 업무지원직이라도 필수요건이 다릅니다</h3>'
                '<div class="review-table"><table><caption>공식 지원자격과 대조한 분야별 인원·필수요건</caption>'
                '<thead><tr><th scope="col">분야</th><th scope="col">인원</th>'
                '<th scope="col">필수요건</th></tr></thead><tbody>' + table_rows
                + '</tbody></table></div>'
                '<p>합계는 66명입니다. 여러 업무가 함께 적힌 2명 모집을 업무마다 2명씩으로 합산하지 마세요. '
                '앞의 다섯 분야는 6개월 근무경험을, 기계·환경처리는 지정 자격증을 먼저 확인해야 합니다. '
                '근무경험만으로 자격증 요건을 대신한다고 해석할 수 없습니다.</p>'
                '<p>정규직도 3개월 수습과 평가 조건이 있습니다. 1차 평가 60점 미만이면 추가 2개월 평가를 거치며, '
                '2차에서도 기준에 못 미치면 임용취소 또는 계약해지가 가능하다고 안내합니다. '
                '합격 후 임용후보자로 대기할 수 있으므로 합격 발표일을 출근일로 단정하지 마세요.</p>'
                '<p>이 표는 모집인원·자격 비교입니다. 각 분야의 상세 담당업무를 새로 검증한 표가 아닙니다. '
                '공고문에서 접수기간 11월 11~20일은 확인했지만 정확한 마감시각은 확인되지 않았습니다. '
                '게시 종료시각을 실제 원서접수 마감시각으로 사용하지 않으며, 마감시각은 기관 공고 확인 필요입니다.</p>')
        conditional_window = verified_application_notice.get('conditional_application_window_label')
        utc_label = verified_application_notice.get('utc_application_window_label')
        # A UTC date-only recruitment window is display-only evidence. Never
        # silently convert it into a KST 23:59 cutoff or mark it time-confirmed.
        reception = (
            '<p>공식 안내에서 확인한 원서접수기간: ' + escape(confirmed_period) + '</p>'
            if confirmed_period else
            ('<p>공식 접수기간(UTC 기준): ' + escape(utc_label) + '</p>'
             if isinstance(utc_label, str) and utc_label else
             ('<p>공식 충원조건부 원서접수 안내: ' + escape(conditional_window) + '</p>'
              if isinstance(conditional_window, str) and conditional_window else ''))
        )
        if proof_url and (reception or field_review):
            application_review_html = (
                '<section id="application-review" aria-label="공식 공고 추가 대조">'
                '<h2>공식 공고와 추가 대조한 지원 정보</h2>' + reception + field_review
                + '<p class="muted">대조 범위: ' + escape(verified_application_notice.get('reader_scope', verified_application_notice.get('scope', '')))
                + '</p><p><a href="' + escape(proof_url, quote=True)
                + '" target="_blank" rel="noopener noreferrer">대조한 공식 원문</a> · 확인일: '
                + escape(proof_date) + ' · 최신 정정 공고가 우선합니다.</p></section>')
            notice_url = safe_url(verified_application_notice.get('notice_source_url'))
            if notice_url:
                application_review_html = application_review_html.removesuffix('</section>') + (
                    '<p><a href="' + escape(notice_url, quote=True)
                    + '" target="_blank" rel="noopener noreferrer">대조한 공식 첨부 공고문</a></p></section>')

    # 표시하는 내용은 ALIO 원본 필드에 존재하는 사실만 사용합니다.
    detail = detail if isinstance(detail, dict) else {}
    qualification = clean(detail.get('aplyQlfcCn'))
    process = clean(detail.get('scrnprcdrMthdExpln'))
    check_items = [
        ('지원 자격', '공고에 기재된 지원 자격을 확인하세요.' if qualification else '상세 자격조건은 공식 채용공고에서 확인하세요.'),
        ('기간 구분', f'ALIO 게시 종료일은 {due_display}입니다. 원서 접수기간·마감시각과 다를 수 있으므로 공식 공고에서 별도로 확인하세요.' if due else '공식 채용공고에서 접수기간과 마감시각을 확인하세요.'),
        ('전형 절차', '아래 채용 절차 항목과 공식 공고의 최신 일정을 비교하세요.' if process else '서류·필기·면접 실시 여부와 일정은 공식 공고에서 확인하세요.'),
    ]
    # 공고별 실제 데이터로 확인 항목을 구성합니다. 확인되지 않은 조건은 추정하지 않습니다.
    if post.get('region'):
        check_items.append(('근무 지역', f'표시된 근무지역은 {clean(post.get("region"))}입니다. 실제 배치 장소와 전근 가능성은 공식 공고를 확인하세요.'))
    if post.get('emp'):
        check_items.append(('고용 형태', f'표시된 고용형태는 {display_employment}입니다. 계약기간과 정규직 전환 여부는 공식 공고를 확인하세요.'))
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
        ('/careerpick/guides/application-checklist.html', '지원 전 7가지 확인사항'),
        ('/careerpick/guides/qualification-preference-guide.html', '지원자격·우대조건 해석법'),
        ('/careerpick/guides/after-application-checklist.html', '지원서 제출 후 확인사항'),
        ('/careerpick/guides/recruitment-corrections-guide.html', '정정공고·마감 변경 대응법'),
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
        guide_items.append(('/careerpick/guides/ncs-study-plan.html', 'NCS 4주 학습 계획'))
    if any(word in context for word in ('자기소개서', '자소서', '서류전형', '입사지원서', '경험기술')):
        guide_items.append(('/careerpick/guides/self-introduction-star.html', 'STAR 자기소개서 작성법'))
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
        if review.get("decision") in ("same_notice", "amended_notice") and other.get("id") in review["peer_ids"]:
            continue
        other_id = clean(other.get('id'))
        if other_id == pid or not re.fullmatch(r'a[0-9]+', other_id):
            continue
        other_title = clean(other.get('title'))
        if not other_title:
            continue
        related_items.append(
            f'<li><a href="/careerpick/jobs/{escape(other_id, quote=True)}.html">'
            f'{escape(other_title)}</a>'
            f' <span class="muted">· ALIO 게시 종료일 {escape(date_label(other.get("due"), other.get("dueHasTime") is True))}</span></li>'
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
    has_substantive_desc = bool(verified_duties)
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
            ('ALIO 게시 종료일', bool(due)),
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
    if verified_duties:
        duties_checklist_html = (
            '<section id="job-duties" aria-label="공식 직무기술서 확인 요약">'
            '<h2>공식 직무기술서에서 확인한 담당업무</h2>'
            f'<h3>{escape(verified_duties.get("reader_scope", verified_duties["scope"]))}</h3>'
            f'<p>{escape(verified_duties["summary"])}</p>'
            f'<p class="source-note">지원 전 비교: {escape(verified_duties["applicant_check"])}</p>'
            '<p>모든 모집분야를 검증한 것은 아닙니다. 위 범위 이외의 담당업무·인원·근무조건은 공식 원문 확인 필요.</p>'
            f'<p class="source-meta">원본 확인일: {escape(verified_duties["checked_on"])} · '
            'AI 원문 대조·요약. 기관의 공식 공고와 최신 정정 내용이 우선합니다.</p>'
            f'<p><a href="{escape(verified_duties["source_url"], quote=True)}" '
            'target="_blank" rel="noopener noreferrer">'
            f'공식 첨부 원문: {escape(verified_duties["source_label"])}</a></p></section>'
        )
    # A notice-specific, source-checked editorial note; never infer HWP duties.
    verified_notice_html = ''
    if (pid == 'a307034' and org == '한전KPS(주)'
            and title == '한전KPS(주) 서울경기전력지사 양주지점 단기노무원(부지정리) 모집'):
        verified_notice_html = (
            '<section id="verified-notice" aria-label="공식 공고 핵심 안내">'
            '<h2>한전KPS 양주지점 부지정리 단기노무원 지원 안내</h2>'
            '<p>부지정리 단기노무원 2명 모집입니다. 일반 사무직이나 정규직 모집이 아닙니다. '
            '공식 공고문 6항의 접수기간은 2026년 11월 16일~11월 20일 16시(KST)이며, '
            '기간 후 접수는 불가하다고 안내합니다. 이메일 또는 우편·방문 접수입니다. '
            '우편 도착 인정 기준과 변경 여부는 공식 담당자에게 확인하세요.</p>'
            '<h3>근무 장소와 면접 장소가 다릅니다</h3>'
            '<p>근무지는 양주지점 관내 송전철탑 주변입니다. 예정 근무기간은 '
            '2026년 12월 1일~12월 31일이며 월별 계약입니다. 기상·회사 사정으로 '
            '미투입되는 날이 있을 수 있고 실제 근로일 기준 계약·근무일 조정이 안내됩니다. '
            '예정 근무시간은 주 5일, 08:00~16:00 중 휴게 1시간을 제외한 7시간입니다. '
            '한 달 전체 근무일수나 임금 총액이 보장된다는 뜻은 아닙니다.</p>'
            '<p>서류접수 → 면접 → 신체검사 → 채용통보 순서이며, '
            '면접은 11월 24일 14시 수원시 영통구 대학3로 20의 서울경기전력지사에서 '
            '진행할 예정입니다. 양주 근무지로 바로 찾아가지 말고 개별 통보를 확인하세요.</p>'
            '<h3>우대 가점은 자동 적용으로 계산하지 마세요</h3>'
            '<p>ALIO 요약에는 각 전형단계 가점으로 기재돼 있지만, 첨부 공고문 4항은 '
            '면접전형 가점으로 설명합니다. 보훈 5~10%, 장애인 5%, 건설업 기초안전보건교육 '
            '수료자 5%가 제시되며, 모집 3명 이하의 보훈 가점 미적용 원칙과 응시자 수에 따른 '
            '예외도 함께 적혀 있습니다. 이 공고는 2명 모집이므로 본인 적용 여부를 담당자에게 '
            '확인해야 합니다. 블라인드 지원서에는 공고에서 금지한 출신학교·가족관계 등 '
            '개인정보와 사진을 넣지 마세요.</p>'
            '<p>채용예정일 즉시 근무할 수 있어야 하며, 공고문은 현장업무 수행 전에 '
            '건설업 기초안전보건교육 4시간 이수를 요구합니다. 직무기술서의 권장 항목만 보고 '
            '교육이 불필요하다고 판단하지 마세요. 우대 증빙 제출 시점도 ALIO 요약과 첨부 '
            '공고문의 표현이 달라 제출 전에 담당자 확인이 필요합니다.</p>'
            '<p class="source-note">AI 원문 대조일: 2026-11-16. 첨부 공고문 1~7항과 '
            '직무기술서를 대조했습니다. 세부 가점과 제출시점 차이를 임의로 해석하지 않았습니다. '
            '공식 정정 공고와 담당자 안내를 함께 확인하세요.</p>'
            '<p><a href="https://www.alio.go.kr/download/download.json?fileNo=3087622" '
            'rel="noopener noreferrer" target="_blank">공식 채용공고문 HWP</a> · '
            '<a href="https://job.alio.go.kr/recruitview.do?idx=307034" '
            'rel="noopener noreferrer" target="_blank">공식 ALIO 공고·담당자 확인</a></p>'
            '</section>'
        )
    if pid == 'a306436':
        verified_notice_html = (
            '<section id="verified-notice" aria-label="공식 공고 핵심 안내">'
            '<h2>안양·부평 우편물구분 채용 확인사항</h2>'
            '<p>공식 ALIO 공고는 안양·부평물류사업소의 기간제(일용직) 우편물구분 분야를 안내합니다. '
            '근무지역은 인천·경기이며, 채용인원은 전체 115명입니다. '
            '사업소별 인원과 근무시간·임금은 첨부 공고문을 확인하세요.</p>'
            '<p>지원자는 우체국물류지원단 인사규정상 결격사유가 없어야 하고, '
            '채용 즉시 근무할 수 있어야 합니다. 전형은 서류심사 후 적격자 면접심사로 진행하며, '
            '적격자가 있으면 즉시 채용될 수 있습니다.</p>'
            '<p class="source-note">ALIO의 2026-11-30은 공고 게시 종료일입니다. '
            '원서접수 마감시각이나 지원 가능 상태를 보증하지 않습니다. '
            '세부 담당업무는 공식 직무기술서 HWP 본문을 확인해야 합니다. '
            '확인한 담당업무 요약과 공식 원문은 아래 별도 항목에서 확인하세요.</p>'
            '<p><a href="https://job.alio.go.kr/recruitview.do?idx=306436" '
            'rel="noopener noreferrer" target="_blank">공식 ALIO 공고 확인</a></p>'
            '</section>'
        )
    if pid == 'a306750':
        verified_notice_html = (
            '<section id="verified-notice" aria-label="공식 공고 핵심 안내">'
            '<h2>코레일유통 물류사업 채용 분야별 지원자격</h2>'
            '<p>모집인원 723명은 공고 전체 인원입니다. 직무별 모집인원·근무장소·근무형태는 '
            '공식 첨부 공고문에서 각각 확인해야 합니다.</p>'
            '<ul class="checks">'
            '<li><strong>부산지점 물류운영 기술직 6급</strong> — 컨테이너크레인운전기능사와 '
            '지게차운전기능사 두 자격 모두 필요</li>'
            '<li><strong>현장안전처 팀장</strong> — 철도 안전계획·안전관리 업무 경력 7년 이상</li>'
            '<li><strong>현장안전처 안전지도사</strong> — 철도 안전지도사 업무 경력 4년 이상</li>'
            '<li><strong>운영관리처 팀장·팀원</strong> — 관련 관리 업무 경력 각각 7년·4년 이상</li>'
            '<li><strong>철도운영단 구내운전직</strong> — 지정 철도차량 운전면허 중 하나와 '
            '철도운영기관 기관사 경력 2년 이상</li>'
            '<li><strong>철도운영단 전호연료직</strong> — 공식 공고에 열거된 철도운영·역무·'
            '신호·정비·급유 등 관련 분야 경력 2년 이상</li>'
            '</ul>'
            '<h3>직종별 연령 기준 날짜가 다릅니다</h3>'
            '<p><strong>만 18세 이상~만 60세 이하:</strong> 공무사무직 라급·기술직 6급은 '
            '2026년 12월 15일, 수송직은 2027년 1월 1일 기준입니다.</p>'
            '<p><strong>만 18세 이상~만 70세 미만:</strong> 스토리지는 2026년 12월 15일, '
            '구내운전직·전호연료직은 2027년 1월 1일, 현장안전처·운영관리처는 '
            '2027년 1월 4일 기준입니다.</p>'
            '<p class="source-note">위 내용은 공식 ALIO 공고의 분야별 지원자격 요약이며 '
            '실제 담당업무를 설명하는 직무기술서가 아닙니다. '
            '담당업무 요약과 직무기술서 원문은 아래 별도 항목에서 확인하세요. '
            '공식 접수마감은 2026년 11월 19일 오전 10시(KST)로 안내됐으며, '
            '정정 여부와 분야별 세부사항은 기관 공고에서 다시 확인하세요.</p>'
            '<p><a href="https://job.alio.go.kr/recruitview.do?idx=306750" '
            'rel="noopener noreferrer" target="_blank">공식 ALIO 공고 확인</a></p>'
            '</section>'
        )
    if pid == 'a306355':
        verified_notice_html = (
            '<section id="verified-notice" aria-label="공식 공고 핵심 안내">'
            '<h2>IBK 체험형 청년인턴 지원 전 핵심 확인</h2>'
            '<p>공식 ALIO 공고의 모집인원은 총 390명이며 체험형 청년인턴입니다. '
            '학력과 전공 제한은 없지만, 청년 연령 기준 및 과거 IBK 청년인턴 근무 이력 제한을 확인해야 합니다.</p>'
            '<p>기본 연령 요건은 2026년 10월 27일 기준 만 19~34세이며, '
            '제대군인은 군 복무기간에 따른 상한 연장 규정이 적용될 수 있습니다. '
            '개별 적용 여부와 결격사유는 공식 공고에서 확인하세요.</p>'
            '<p>전형은 지원서 접수 및 AI역량검사 → 서류심사 → 실기시험 순서입니다. '
            'AI역량검사 미응시자는 서류심사 불합격 처리된다고 안내되어 있습니다. '
            '최종 실기시험은 발표·토론 및 심층인터뷰를 포함합니다.</p>'
            '<p class="source-note">공식 원서접수 마감은 2026년 11월 16일 오전 10시(KST)입니다. '
            '지원 가능 여부·정정 여부는 채용기관 공식 사이트에서 재확인하세요. '
            '분야별 담당업무 요약과 공식 직무기술서 PDF는 아래 별도 항목에서 확인하세요.</p>'
            '<p><a href="https://job.alio.go.kr/recruitview.do?idx=306355" '
            'rel="noopener noreferrer" target="_blank">공식 ALIO 공고 확인</a></p>'
            '</section>'
        )
    # Structured editorial notes inherit the exact source identity check above.
    # Metadata contains plain text only; never insert source text as HTML.
    sections = verified_duties.get('notice_sections', [])
    notice_source = safe_url(verified_duties.get('notice_source_url'))
    if isinstance(sections, list) and sections and notice_source:
        parts = []
        for section in sections:
            if not isinstance(section, dict) or not isinstance(section.get('heading'), str):
                continue
            paragraphs = section.get('paragraphs', [])
            if not isinstance(paragraphs, list):
                continue
            parts.append(f'<h3>{escape(section["heading"])}</h3>')
            parts.extend(f'<p>{escape(value)}</p>' for value in paragraphs
                         if isinstance(value, str) and value.strip())
        if parts:
            # Preserve previously verified guidance and unique anchors when adding detail.
            section_id = 'verified-notice-supplement' if verified_notice_html else 'verified-notice'
            checked_on = verified_duties.get('notice_checked_on', verified_duties['checked_on'])
            verified_notice_html += (
                f'<section id="{section_id}" aria-label="공식 공고 핵심 안내">'
                '<h2>공식 원문과 대조한 지원 안내</h2>' + ''.join(parts)
                + f'<p class="source-meta">공고문 확인일: {escape(checked_on)} · '
                'AI 원문 대조·요약. 최신 정정 공고가 우선합니다.</p>'
                + f'<p><a href="{escape(notice_source, quote=True)}" target="_blank" '
                'rel="noopener noreferrer">공식 공고문 원본: '
                + escape(verified_duties.get('notice_source_label', '공고문'))
                + '</a></p></section>'
            )
    coverage_html = (
        '<section aria-label="공고 정보 제공 범위"><h2>공고 정보 제공 범위</h2>'
        f'<p class="source-note">{escape(coverage_note)}</p></section>'
    )

    # A single source-check checklist is rendered above; avoid duplicate boilerplate.
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
    snapshot_at = clean(post.get('_snapshot_at')) or '미확인'
    source_html = (
        '<p class="source-meta">자료 출처: ALIO 제공 데이터 · '
        f'자료 묶음 조회 시각: {escape(snapshot_at)} · 개별 첨부 원문의 사람 검토 시각이 아닙니다. '
        '게시기간과 원서 접수기간은 다를 수 있습니다. 최신 수정·접수 정보는 공식 원문에서 확인하세요.</p>'
    )

    # 공고마다 고유한 확인 가능 정보로 설명을 구성합니다.
    # 직무 분류처럼 짧은 원본 설명만으로는 채용 내용을 설명하기 어렵습니다.
    desc = clean(post.get('desc'))
    summary_parts = [
        f'{org}의 {title} 채용공고입니다.',
        f'고용형태: {display_employment}.' if post.get('emp') else '',
        f'근무지역: {clean(post.get("region"))}.' if post.get('region') else '',
        f'모집인원: {count_label(post.get("n"))}.' if post.get('n') else '',
        f'ALIO 게시 종료일: {due_display}. 실제 접수마감은 원문 확인.' if due else '',
    ]
    # ALIO desc는 NCS 직무 분류이며 실제 담당업무가 아닙니다.
    is_category_only = bool(desc)
    if qualification:
        summary_parts.append('지원자격: ' + qualification[:900])
    if process:
        summary_parts.append('전형 절차: ' + process[:500])
    # Only the original-backed, source-identity-bound duty review may enrich
    # JobPosting description; generic ALIO NCS categories are not duties.
    # This must disappear when the notice ID, title, seats or end date changes.
    if verified_duties.get('strict_source_identity') is True:
        duty_summary = clean(verified_duties.get('summary'))
        if duty_summary:
            summary_parts.append('공식 직무기술서 검토 범위: ' + duty_summary)
    # Google requires paragraph-formatted HTML for JobPosting description.
    # Escape all source text; the JSON-LD serializer below also neutralizes '<'.
    job_description = ''.join('<p>' + escape(part) + '</p>'
                              for part in summary_parts if part)

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

    if application_cutoff:
        # Only exact-source-verified application cutoffs may override the ALIO
        # publication end date in Google JobPosting structured data.
        schema['validThrough'] = application_cutoff
    elif deadline:
        # A date-only ALIO publication end is not a verified application
        # cutoff. Keep it separate from the searchable JobPosting lifecycle.
        schema['validThrough'] = (
            deadline[:10] if post.get('dueHasTime') is not True else deadline
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

    # Google FULL_TIME means verified full-time hours, not Korean regular
    # employment status. ALIO 정규직 is a contract classification and does
    # NOT by itself prove full-time hours; omit employmentType for that case.
    # Contract/intern labels may be mapped only when the role is unambiguous.
    # Never infer TEMPORARY for 무기계약직 or a mixed employment listing.
    if post.get('emp'):
        raw_employment = ([verified_application_notice['confirmed_employment']]
                          if verified_application_notice.get('confirmed_employment') else post['emp'])
        kinds = raw_employment if isinstance(raw_employment, list) else [raw_employment]
        unique_kinds = {clean(kind) for kind in kinds if clean(kind)}
        # 한 공고 안에 정규직·계약직이 같이 있으면 직무별 고용형태를 알 수 없어 생략.
        if len(unique_kinds) == 1:
            employment = next(iter(unique_kinds))
            employment_type = {
                '계약직': 'TEMPORARY',
                '인턴': 'INTERN',
            }.get(employment)
            if employment_type:
                schema['employmentType'] = employment_type

    # 마감된 공고는 JobPosting 구조화 데이터를 제거합니다.
    # 안내용 HTML 페이지는 그대로 유지합니다.
    # Publication end dates are not verified application deadlines. Keep the
    # useful HTML, but do not emit a JobPosting with an invented validThrough.
    # An employer-confirmed future reception window is not yet an open
    # application opportunity, even though its notice page is public.
    verified_reception_not_open = bool(
        verified_start and parsed_start
        # Calendar-only start dates are KST, not the runner's local timezone.
        and datetime.fromisoformat(
            parsed_start if 'T' in parsed_start else parsed_start + 'T00:00:00+09:00'
        ).astimezone(timezone.utc) > datetime.now(timezone.utc)
    )
    schema_json = '' if (duplicate or robots_noindex or verified_reception_not_open
                         or verified_application_notice.get('source_headcount_conflict') is True
                         or (not application_cutoff and post.get('dueHasTime') is not True)) else (
        '<script type="application/ld+json">'
        + json.dumps(
            schema,
            ensure_ascii=False
        ).replace('<', '\\u003c')
        + '</script>'
    )

    notice = (
        '<p class="closed">'
        + ('공식 확인된 원서접수 마감시각이 지난 보관 공고입니다. '
           if application_cutoff else '표시된 종료일이 지난 보관 공고입니다. ')
        +
        '실제 접수 종료·연장 여부는 공식 공고를 확인하세요.'
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
        meta_parts.append('고용형태 ' + display_employment)
    if due:
        meta_parts.append('ALIO 게시 종료일 ' + due_display + ' · 접수마감 원문 확인')
    meta_description = ' | '.join(meta_parts)[:155]

    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} | {escape(org)} | 커리어픽</title>
<meta name="description" content="{escape(meta_description, quote=True)}">
{'<meta name="robots" content="noindex,follow">' if robots_noindex else ''}
<link rel="canonical" href="{escape(canonical, quote=True)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{escape(title, quote=True)}">
<meta property="og:url" content="{escape(canonical, quote=True)}">
{schema_json}
<style>
body{{margin:0;background:#f5f7fb;color:#14213d;font:16px/1.7 system-ui,'Malgun Gothic',sans-serif;overflow-wrap:anywhere}}
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
.review-table{{overflow-x:auto}}.review-table table{{border-collapse:collapse;width:100%;font-size:14px;table-layout:fixed}}.review-table td,.review-table th{{border:1px solid #cbd5e1;padding:8px;overflow-wrap:anywhere;vertical-align:top}}.review-table th:nth-child(2),.review-table td:nth-child(2){{width:3em}}.review-table caption{{text-align:left;padding:8px 0}}
html{{scroll-behavior:smooth}}
section[id],h2[id]{{scroll-margin-top:20px}}
@media(max-width:480px){{dl{{grid-template-columns:1fr;gap:0}}dt{{border:0;padding-bottom:0}}dd{{padding-top:0}}}}
@media(max-width:760px){{main{{margin:0;border-radius:0;padding:20px}}h1{{font-size:1.4rem}}section h2{{font-size:1.2rem}}.apply{{display:block;text-align:center;overflow-wrap:anywhere}}.guide-links a{{flex:1 1 auto;text-align:center}}}}
</style>
</head>
<body>
<a class="skip-link" href="#job-summary">본문으로 바로가기</a>
<main>
<nav><a href="/careerpick/">← 커리어픽 전체 채용공고</a></nav>
<p class="muted">공공기관 채용정보</p>
<h1>{escape(title)}</h1>
<p>{escape(org)}</p>
{source_html}
{notice}
{toc_html}
{review_html}
<h2 id="job-summary">모집 요약</h2>
<dl>{rows}</dl>
{conflict_html}

{f'<section><h2>직무 분류</h2><p>{escape(desc)}</p><p class="muted">직무 분류는 실제 담당업무 설명이 아닙니다. 세부 직무는 공식 공고를 확인하세요.</p></section>' if is_category_only else ''}
<section id="job-checks" aria-label="지원 전 핵심 확인사항">
<h2>지원 전 핵심 확인사항</h2>
<ul class="checks">{checks}</ul>
</section>
{coverage_html}
{application_review_html}
{verified_notice_html}
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
<a href="/careerpick/">다른 채용공고 찾아보기</a>
<footer aria-label="사이트 안내">
<p class="muted">커리어픽은 공식 채용공고를 안내하는 정보 서비스이며, 채용기관을 대신해 지원서를 접수하지 않습니다.</p>
<nav class="guide-links" aria-label="사이트 정책 및 연락처"><a href="/careerpick/about.html">사이트 소개</a><a href="/careerpick/privacy.html">개인정보처리방침</a><a href="/careerpick/contact.html">문의하기</a></nav>
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

    notice_reviews = resolve_notice_reviews(posts, details)
    OUT.mkdir(exist_ok=True)
    created = 0
    quality = {
        'total': 0,
        'verified_editorial_duty_reviews': 0,
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
        item_review = notice_reviews.get(item_id, {})
        if item_review.get('decision') == 'same_notice' and item_review['representative_id'] != item_id:
            continue
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
        # Only an explicit, nonempty source field counts as substantive duties.
        # NCS/category labels in the list feed must never be counted as duties.
        has_description = bool(clean(job_detail.get('jobDscrptn')))
        editorial = VERIFIED_DUTIES.get(pid, {})
        editorial_reviewed = (
            editorial.get('organization') == clean(post.get('org'))
            and editorial.get('title') == clean(post.get('title'))
        )
        quality['verified_editorial_duty_reviews'] += int(editorial_reviewed)
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
        # Editorial review queue only: never suppress, invent, or rewrite notice data.
        # Prioritize open notices with missing official sources and essential details.
        is_current = bool(post.get('due')) and not is_closed(post.get('due'))
        review_reasons = []
        if not has_official:
            review_reasons.append('official_source_missing')
        if not has_qualification:
            review_reasons.append('qualification_missing')
        if not has_process:
            review_reasons.append('selection_process_missing')
        if not has_description:
            review_reasons.append('substantive_duties_missing')
        review_priority = (
            'high' if is_current and (not has_official or (not has_qualification and not has_process))
            else 'medium' if is_current and review_reasons
            else 'low'
        )
        quality_rows.append({
            'is_current_by_source_end_date': is_current,
            'review_priority': review_priority,
            'review_reasons': review_reasons,
            'id': pid,
            'title': clean(post.get('title')),
            'organization': clean(post.get('org')),
            'recruitment_count_raw': clean(post.get('n')),
            'recruitment_count_verified_numeric': int(clean(post.get('n'))) if re.fullmatch(r'[0-9]+', clean(post.get('n'))) else None,
            'source_end_date': clean(post.get('due')),
            'official_source_url': official_url,
            'official_link_host': (urlparse(official_url).hostname or '') if official_url else '',
            'official_link_status': 'url_format_ok_not_live_checked' if official_url else 'missing_or_invalid',
            'missing': missing,
            'detail_fields': {
                'qualification': has_qualification,
                'process': has_process,
                'substantive_description': has_description,
                'verified_editorial_duties': editorial_reviewed,
                'editorial_review_scope': editorial.get('scope', '') if editorial_reviewed else '',
            },
        })

        target = OUT / f'{pid}.html'
        html = render(dict(post, _snapshot_at=raw.get('updated', '')), job_detail, by_org.get(clean(post.get('org')), ()), notice_reviews.get(pid))

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
    quality['original_review_page_ids'] = len(notice_reviews)
    quality['confirmed_duplicate_alias_pages'] = sum(v.get('representative_id') != pid for pid, v in notice_reviews.items() if v['decision'] == 'same_notice')
    quality['verified_editorial_unique_notices'] = len({(notice_reviews[pid]['representative_id'] if notice_reviews.get(pid, {}).get('decision') == 'same_notice' else pid) for row in quality_rows if row['detail_fields']['verified_editorial_duties'] for pid in [row['id']]})
    quality['official_original_review_groups'] = len({tuple(v['peer_ids']) for v in notice_reviews.values()})
    quality['unreviewed_duplicate_candidate_groups'] = sum(not set(g['ids']).issubset(notice_reviews) for g in suspected_duplicates)
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
        'review_queue': sorted(
            [row for row in quality_rows if row['review_priority'] != 'low'],
            key=lambda row: (
                {'high': 0, 'medium': 1}[row['review_priority']],
                -(row['recruitment_count_verified_numeric'] if row['recruitment_count_verified_numeric'] is not None else -1),
                row['organization'], row['id'],
            ),
        ),
        'posts': quality_rows,
        'suspected_duplicates': suspected_duplicates,
    }
    # Make the editorial workload measurable without changing public indexing.
    report['review_summary'] = {
        'current_by_source_end_date': sum(row['is_current_by_source_end_date'] for row in quality_rows),
        'high_priority': sum(row['review_priority'] == 'high' for row in quality_rows),
        'medium_priority': sum(row['review_priority'] == 'medium' for row in quality_rows),
        'low_priority': sum(row['review_priority'] == 'low' for row in quality_rows),
        'current_missing_duties': sum(
            row['is_current_by_source_end_date'] and
            'substantive_duties_missing' in row['review_reasons']
            for row in quality_rows
        ),
        'review_queue_count': len(report['review_queue']),
    }
    print('접수 종료일 기준 콘텐츠 검토 우선순위:', json.dumps(report['review_summary'], ensure_ascii=False))
    # A short, actionable sample in CI logs; full queue remains in the artifact.
    # These are source-provided candidates, not independently verified openings.
    report['review_top_10'] = report['review_queue'][:10]
    print('채용인원 우선 공식 원문 검토 후보 10건:',
          json.dumps([{
              'id': row['id'],
              'organization': row['organization'],
              'title': row['title'],
              'recruitment_count_raw': row['recruitment_count_raw'],
              'source_end_date': row['source_end_date'],
              'official_source_url': row['official_source_url'],
              'review_reasons': row['review_reasons'],
          } for row in report['review_top_10']], ensure_ascii=False))


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
        'due': '2099-10-28', 'dueHasTime': True, 'n': 3, 'alio': True,
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
    assert '<dt>ALIO 게시 종료일 · 접수마감 원문 확인</dt><dd>2099-10-29</dd>' in date_only_html
    assert '2099-10-29 23:59' not in date_only_html
    date_only_jsonld = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        date_only_html, re.S
    )
    assert not date_only_jsonld, 'Publication end date is not a verified application deadline'
    with_verified_time = dict(date_only, dueHasTime=True)
    with_time_html = render(with_verified_time, {})
    assert '<dt>ALIO 게시 종료일 · 접수마감 원문 확인</dt><dd>2099-10-29 23:59</dd>' in with_time_html
    with_time_jsonld = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        with_time_html, re.S
    )
    assert with_time_jsonld
    assert json.loads(with_time_jsonld.group(1))['validThrough'] == '2099-10-29T23:59:00+09:00'
    # Regular employment is not proof of full-time hours; the visible
    # category stays in the page, but the optional JSON-LD field is omitted.
    # Other types require an unambiguous source classification.
    for employment, expected in (
        (['정규직'], None),
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
    assert '/careerpick/jobs/a12346.html' in related_html
    assert '&lt;b&gt;다른 공고&lt;/b&gt;' in related_html
    assert 'href="/careerpick/jobs/a12345.html"' not in related_html
    assert 'href="/careerpick/jobs/invalid.html"' not in related_html
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
    assert '표시된 종료일이 지난 보관 공고입니다' in closed_html
    assert 'type="application/ld+json"' not in closed_html
    assert '<meta name="robots" content="noindex,follow">' in closed_html
    sample['due'] = '2099-01-01'
    open_html = render(sample, {})
    assert '<meta name="robots" content="noindex,follow">' not in open_html
    sample['due'] = '2020-01-01'
    # 동일한 입력은 동일한 HTML을 생성해야 합니다.
    assert render(sample, {}) == closed_html
    print('CareerPick job-page regression checks: PASS')


if __name__ == '__main__':
    import sys
    if '--self-test' in sys.argv:
        self_test()
    else:
        main()



