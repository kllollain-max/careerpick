# 커리어픽 Threads v6.0 — cleaneye-81220 안성시시설관리공단 공식 채용포털 독립 검수 (HOLD)

- 공식 조회일: 2026-11-18 KST (이번 회차 외부 공식 게시판 직접 확인)
- 공고: 안성시시설관리공단 2026년도 제5회 직원 채용 공고, 공식 채용게시판 **1720번** (등록 2026-11-13)
- 기관 공식 채용 및 접수 화면: https://www.asimc.or.kr/portal/recruit/notice/list.do?mid=0302010100
- Cleaneye canonical ID: `cleaneye-81220`, https://job.cleaneye.go.kr/user/ypCareersData.do?idx=81220
- 기관 원본 화면의 현재 상태: **모집중**, 접수 **2026-11-17 09:00 ~ 2026-11-23 17:00 KST**, 총 모집 규모 **7명** (직무별/고용형태 미분리).
- 같은 공단 1723번은 **제4회 기간제 정정 공고**로 별개다. 이를 제5회 공고 정정으로 오인해서는 안 된다.
- 비공식 요약 사이트에 `일반행정 7급 1명`이라고 적혀 있어 **독립 원문 대조 검증 대상으로 선정**, 기관 세부 공고문/첨부 전문을 아직 확보하지 못해 고용형태·직무별 인원·자격을 **확정하지 않는다**.
- 모집 종료일의 비공식 `23:59` 표기는 기관 공식 포털의 **17:00**과 불일치하므로 채택 금지.

## v5 문안 예비안 — 미승인 / 미등록 / 비게시

```text
경기도 공공기관 채용 소식!

안성시시설관리공단이 2026년 제5회 직원 채용을 진행 중이에요.
공식 채용시스템에는 전체 모집 7명으로 안내돼 있어요.

접수는 11월 23일 17시까지입니다.
지원 전 직무별 인원, 고용형태와 필수 자격을 공고 원문에서 확인하세요.

자세한 사항은 프로필링크 확인
```

**승인 금지(HOLD)**: 단순 포털 리스트와 수집 해시만으로 의미 검증을 주장하지 않음. 기관 원본 첨부(PDF/HWP) 전체 독립 열람, 7명 구성 중 실제 정규직 직무별 인원과 지원자격/우대/변경·취소의 정확한 확인, 공식 신청 상세 URL 및 프로필 표시 검증, 기한 내 근거 재검증, `validate_entry`, 해당 슬롯 TEXT/IMAGE와 카드 원본 픽셀 검사, 원격 `reviewed-submissions`→ingest→queue CAS를 모두 통과해야 실공급 가능. 기존 11/18 08·12·16·20 슬롯 및 게시 계정과 타 브랜드/홈페이지/수집/검색/푸시는 절대 변경 금지.

## 다음 조치

기관 1720번 게시물 클릭에 필요한 HTML 원본 버튼/링크 및 공고 첨부 원본을 찾아 별도 읽기 전용 workflow에서 수신증을 검증. 실제 다운로드·전문 판독 전에는 SHA나 검토시각을 생성해 승인하지 않는다.

## 2026-11-18 03:49~03:52 KST — 실제 공식 HTML 원본 수신·상세 조회 결과

**공식 채용 포털 HTML 원본을 실제 독립 다운로드했다.** [Actions run 44151987199](https://github.com/kllollain-max/careerpick/actions/runs/44151987199) `completed/success`, 공식 GET 200, 원본 HTML **192,159 bytes**, SHA-256 `f7bad32ce4f4b98795f573d0fc740be43b7b1173ea04c8b0628d25fd1cf75db1`. 해당 실행 시 1720번 원문의 실제 상태 `모집중`, 지원 `3/7`, 2026-11-17 09:00~2026-11-23 17:00, 등록 11/13을 파싱했다. `1723` 제4회 기간제 정정 공고는 별개의 row임.

기관 원본 DOM에서 실제 클릭 참조를 특정했다: 게시번호 `1720` → 앵커 `data-req-form-id=view`, `data-req-merge-form-id=list`, `data-req-p-idx=1745`, `onclick=yhLib.inline.post(this)`. 정확한 POST 대상은 **https://www.asimc.or.kr/portal/recruit/notice/view.do?mid=0302010100** 이며 공식 게시판의 내부 `pIdx`는 **1745**이다. 이 두 숫자를 혼동하지 않는다.

별도 **실제 조회** [run 44152232401](https://github.com/kllollain-max/careerpick/actions/runs/44152232401)와 원본 `list` 폼의 `currentPageNo,recordCountPerPage,keyword,state,keywordType`를 함께 병합해 요청한 [run 44152403657](https://github.com/kllollain-max/careerpick/actions/runs/44152403657)은 HTTP 200을 받았지만, 공고명·첨부가 없는 빈 상세 틀만 수신됐다. 마지막 상세 원본 SHA-256 `20e32f34d54da46b0cd73f8958dd4be15390eec53beb32b9e7125943af8ba371`, 185,771 bytes. **서버 200이나 폼 발견을 공식 상세 의미검증 성공으로 표시하지 않는다.** 실행 검증 단계는 실제 `OFFICIAL_NOTICE_BODY_MISSING`으로 실패 처리하고 영수증 artifact를 보존했다.

따라서 현재는 **공식 목록/접수시간·모집 총수 수신 성공, 상세 PDF/HWP·직무별 정규직 인원·자격·정정 전수·접수 상세 URL 독립검증 실패, 승인 0/CAS 0/게시 0**. 원격 상태의 기존 4개 준비 원고를 유지하고 앞으로 공식 상세의 정확한 로딩 경로를 해결하기 전까지 `cleaneye-81220` 승인 금지.
