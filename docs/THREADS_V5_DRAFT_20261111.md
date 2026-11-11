# Threads v5.0 — 승인 전 Draft

이 변경은 운영 적용 완료가 아니다. main/원격 큐/청구/원장/계정/예약을 수정하지 않는다.
현재 승인된 정책과 READY/예약은 그대로 운영한다. editorial_v5.enabled=false 및 effective_at=null은 의도적인 승인 경계다.
별도 승인 후 최신 상태·동시 실행·미착수 범위를 다시 확인하고, 기존 READY/예약 원고의 정확한 fingerprint를 preserved_entry_sha256에 동결한 후 실제 활성시각을 지정해야 한다. 이전 원고를 수정하거나 해시를 재계산하여 보존 목록에 대체하지 않는다.

## 변경

- threads/prompts/reach-v5.txt: 최신 사용자 지침과 출력 계약. 기존 원문 프롬프트와 함께 실제 writer 입력에 제공한다.
- threads/writer-policy.json: v5 경로·SHA·비활성 승인 경계. 기존 CTA·형식·publication_style과 프롬프트는 보존.
- scripts/threads_v5.py: 300/예외350자, 새 CTA, 첫2줄 기관, 짧은 문단, 반복/과장/URL 검사, 필수제한·모집단위 근거, 단독 본문, 이미지 카드.
- scripts/threads_writer_queue.py: v5 신규 원고 분기. 기존 source/application/profile/image/history/slot/CAS 경계 유지. v5 검수로 사실 미확인 통과 불가.
- scripts/threads_auto.py: 신규 v5만 single_main_v5, 상세답글0. 기존 compact 본문+상세답글 경로 그대로.
- scripts/threads_writer_input.py: v5 원문 입력·승인 후 시간대 형식·실제 publisher 미리보기 연결.
- scripts/threads_candidate_selection.py: 승인 후 분야 순서 적용, 전체 검토 후 제한 및 사용자 선호 근거 audit. 임의 인기점수 없음.
- scripts/threads_performance.py: 신규 v5는24h/72h GET 계획, 본문길이·첫문장·규격 메타데이터. 미제공 클릭/팔로우는null, 기존7d/A-B 비교는별도 보존.
- .github/workflows/threads_auto.yml: 기존 게시기의 v5 카드 함수 선택만 추가. 예약·토큰·권한·일일상한·D단계는 그대로.
- tests/test_threads_v5.py 및 docs/evidence/threads-v5/: 회귀검사·테스트 원고4건·이미지4건.

## 원고 테스트

기존 공식 검수 증거를 보존한 편집용 예시다. 새 현재확인·READY·새 슬롯 예약·큐등록·실제 게시가 아니다.
지원조건과 당일 마감/정정/사이트 일치 여부는 실제 사용할 때 새로 검수한다.
기존 게시글과 같은 공고이므로 이 예시를 새 게시물로 보내지 않는다.

| 시간대 형식 | 예시 | 이전 최종 본문 | v5 예시 |
|---|---|---:|---:|
| 08 핵심정보 | 서울대치과병원 치과위생사4 |340|251|
| 12 자격판단 | 한국노동연구원 연구3 |224|198|
| 16 실제특징 | 충남개발공사 건축3 |317|271|
| 20 주의사항 | 근로복지공단 간호사3 |289|236|

기관·직무 확대, 텍스트 기반1080×1080 JPEG, 고용·인원·실제 마감만 카드 하단에 표시.
실제360px 시안4건을 확인했다. 기존 renderer의 한글지원·잘림 방지·정상JPEG·8MB검사 사용, 임시파일 검사 후 교체.
공개URL/해시는 실제 정규 게시기의 기존 preflight에서 검증하며 이번에는 업로드·게시하지 않았다.

## 검증과 제한

무료 로컬 unittest만 실행. GitHub Actions dispatch/rerun/유료 사용 없음.
Draft 커밋의 [skip ci]는 이 사용자 요청의 유료 Actions 금지를 위한 것이며 CI workflow나 보호규칙을 삭제/완화하지 않는다.
7개 신규 테스트는 CTA/상한/링크/반복/정확한 활성경계/원고 보존/사실증거/미리보기/수집 신선도/단독본문/24h·72h 계획을 검사한다.
기존 포함 Threads170개 및 복원18개, 총188개를 통과했다. AST/YAML/프롬프트SHA와 운영큐의 비활성 상태 검증도 통과했다. 실제 POST는 모두 모의 객체다.

실제 v5 게시/24h·72h 성과는없다. 팔로우·프로필클릭·사이트유입의 글별 귀속은 API가 제공할 때만 측정한다.
충분한 표본에서의 성과 평가·분야 예외 판단·비중 자동 변경은 운영 데이터가 쌓인 후 검토하며 지금 승자나 개선효과를 주장하지 않는다.
별도 승인 필요: Draft 검토/병합, 최신 READY 지문 동결, 실제 활성시각과 enabled 변경, 운영 적용 후 자연 회차 검증.
