# Threads v6.0 독립 공식근거 검토 — cleaneye-80711 (HOLD)

- 작성일: 2026-11-19 (KST)
- 대상: 충주시시설관리공단, 2027년 제1회 직무중심 정규직 공개채용, 공단 공고 제2026-97호
- 기본 대상: `cleaneye-80711`
- 상태: **미승인 독립검토 초안. 발행 및 writer-queue/승인스테이징 등록 금지**
- 원격 main 분기기준 SHA: `8db5eec9b9262a603241b26351feba427440d9ac`

## 현재 독립 확인한 공식자료

1. 공단 직접 채용게시판: https://www.cjfmc.or.kr/www/selectBbsNttView.do?bbsNo=7&integrDeptCode=&key=113&nttNo=15610&pageIndex=1&searchCnd=all&searchCtgry=&searchKrwd=
   - 2026-10-26자 공단 제2026-97호. 기관 직접 지원사이트가 `https://cjfmc.jobnlab.co.kr`이라고 명시, 원문 PDF/HWP 첨부 존재.
   - PDF 첨부 직접 링크: `https://www.cjfmc.or.kr/www/downloadBbsFile.do?atchmnflNo=3566`. 이 실행환경에서는 `application/octet-stream`으로 제공되어 **바이너리 본문 다운로드와 SHA256 검증 실패**. 첨부를 읽었다고 주장하지 않음.
2. 공식 지정 ATS: https://cjfmc.jobnlab.co.kr/jobnotice/view/?recruitid=1007
   - '진행중인 채용' 공고 확인. 게시 화면은 이미지 중심이며, http로 볼 수 있는 HTML에는 직무별 인원·마감시각 텍스트 없음.
   - 실제 입력 시작 화면: https://cjfmc.jobnlab.co.kr/application/reg/auth/?recruitid=1007. 본인 인증/개인정보 입력은 수행하지 않음.
   - 기관 지정 ATS 공지: https://cjfmc.jobnlab.co.kr/board/notice/ (이번 조회에서 별도 공지 0건). 다른 채널 정정·취소 전수확인은 미완료.
3. 공공 고용24 공식 정보제공처(클린아이): https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?infoTypeCd=CLE&infoTypeGroup=tb_workinfocle&wantedAuthNo=20261026021052
   - 일반정규직 신입 전체 13명. 서류·필기·면접. 접수일 2026-11-02~2026-11-23(날짜만 표시).
   - 충주시 지역제한은 **행정직과 일반업무직**에 적용된다고 명시. 전체 13명이 동일 자격이나 동일한 직무라는 해석 금지.
   - '대체인력 구분' 표기가 있어 정규직과 충돌 여부는 원문으로 추가 해소 필요.
4. 운영 handoff의 기존 `cleaneye-80711`은 미검수 후보이고 모집단위 인원 `unit_count_unconfirmed`. 원문 hash는 기존 수집값이지 **원문 독립 의미검수 증빙이 아님**.

## Threads v5 단일본문 — 301자 원고 초안

충주 지역 정규직 채용을 찾는다면 확인해 보세요.

충주시시설관리공단이 2027년 제1회 직무중심 정규직 공개채용을 진행해요. 공식 채용정보에 표시된 전체 모집인원은 13명이며 신입 채용이에요.

행정직·일반업무직에는 충주시 지역제한이 적용돼요. 모든 직무에 같은 지역조건이 적용되는 것으로 오해하지 않도록 지원 분야별 기준을 확인하세요.

지원은 기관 지정 채용사이트를 통해 온라인으로 받고 11월 23일 마감 예정이에요. 직무별 인원·필수자격·정확한 마감시각은 공식 첨부 공고에서 추가 확인이 필요해요.

자세한 사항은 프로필링크 확인

## 초기 문구 점검 (승인 아님)

- 301 유니코드 코드포인트, CTA 정확히 한 번, 본문 URL·도메인·해시태그 0건, 자동답글 0건 의도.
- 전체 **13명**을 특정 직무 인원인 것처럼 쓰지 않음. 직무별 확인을 요청하는 미승인 초안.
- 첨부 원문 자체의 전체 직무별 인원/필수·우대 자격/정확한 시각/변경·취소 검증 불완전. **생산 validate_entry, verify_official_receipt, 포털 프로필 링크, IMAGE 카드, 24h 신선도, CAS 테스트 전부 미실행.**
- 원본 PDF 검증 또는 문구 수정 없이 승인자료 `reviewed-submissions.json`에 기입하거나 큐로 이동 금지.
- 이 변경은 검토 문서 1개만 별도 브랜치에 추가하며, 기존 `@hid_119` 승인 슬롯·큐/Meta·홈페이지·수집·검색·웹푸시·타 브랜드 미변경.

## 실제 승인으로 진행하기 전 필요한 검증

원본 PDF/HWP 전문을 실제 확보·읽고 SHA를 기록해 각 직무별 채용인원과 필수·우대자격·고용형태 구분, 접수 마감시각과 공고 정정/취소 이력을 확인한다. 기관 지정 접수시스템의 개별 직무 화면 및 커리어픽 프로필 표시와 대조한다. 게시 슬롯 24시간 이내 근거를 **실제 재조회한 시각**으로만 갱신한다. 형식이 IMAGE라면 카드 1080/360 픽셀 검증을 완료하고 `validate_entry`·`verify_official_receipt`·production CAS가 모두 통과한 경우에만 등록한다.
