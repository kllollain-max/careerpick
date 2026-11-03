# 최신 실검증 후속 — 토큰 등록 이후

- 실제 Meta GET run41598232621 success: hid_119 / 계정ID28818095904512513, 전체 목록185건. 152건의 목록 차이는 모두 신규 미확정 게시를 뜻하지 않음.
- 후속 run41598910642 success: 10/31 08시 본문18029250455877919 및 상세17909910720593443/참여18132626512765431의 root_post/replied_to가 모두 본문과 일치.
- 11/2 객체18120384022755046은 REPOST_FACADE이며 신규 자동 채용 본문으로 집계하지 않음. quota_usage=0 확인(조회 시점 기간 기준).
- 원본39행 전체를 내용 그대로 유지하고 Meta로 확인한 08시 기록1행만 추가, 합계40행(게시34/실패6). 기존 슬롯/runID는 과거 승인·실운영 증거 기준이고, original reservation time 미확인임을 record에 명시.
- 기존 건강증진개발원 a306146은 공식 기관/제목의 과거 본문18117080909061367과 일치해 추가 선택 제외. 이 관측을 새 accepted 영수증으로 만들지 않음.
- 공개된 계정ID는 API 확인값을 workflow에 연결. 별도의 USER_ID Secret 입력 불필요. 토큰 원문은 읽기/출력하지 않음.
- 과거 원격 accepted 원본은 확보하지 못했으므로 08시 구 슬롯은 historical_verified 관측 파일로만 보호. 새 정규 실행의 accepted 영수증과 구분.
- 기존 저장소는 현재 연결의 GET404, 마지막 확인 계정 정지403 보존. 기존 워크플로 disabled 상태 직접 확인은 불가. 구 코드 timeout18분과 마지막 자동 본문10/31 이후 경과, 공식 계정 정지 시 schedule actor 중단 안내를 함께 기록하며 disabled 확인으로 과장하지 않음. 구 저장소가 복구되면 기존 publisher를 재개하지 말고 먼저 중지/대조해야 함.
- 현재 실제 게시 게이트는 계속 OFF. 아래 초기 미등록 안내는 이전 단계 기록이며 위 실제 확인이 우선.

# Threads 새 저장소 이전

수정 담당: GPT (이 PR). 다른 홈페이지·수집 복구 PR과 별도 범위.

사용자 요청: `kllollain-max/careerpick`으로 이전해 기존 자동 게시 재개.
기준 main: fd47c198a27e2be65a2dee5c0213a3595a9973e6.

## 복원·보존

- 출처: CareerPick_emergency_recovery_backup_20261031.zip의 `snapshots/main-local-161b601`.
- 기존 게시기·계정 hid_119 확인·원격 create-only 청구/accepted 기록·슬롯 중복 방어 재사용.
- KST 08/12/16/20 하루4회. 신규 D 콘텐츠는 workflow에서 false 고정.
- 원본 이력 39행(게시33/실패6)을 바이트 그대로 복원. 최신 이력이라고 간주하지 않음.
- 10/31 08시 기존 검증 본문18029250455877919·답글17909910720593443/18132626512765431은 백업에 없으며, 실제 Meta GET 대조 전 합성 기록이나 accepted 영수증을 만들지 않음.
- 새 이미지 경로는 이 저장소 main의 공개 raw JPEG. 이미지 commit→HEAD 확인→게시 순서를 유지. 실패 시 기존 게시기의 요청 전 텍스트 폴백. 홈페이지 배포·공개 허용목록·다른 자동화는 수정하지 않음.
- 기존 hostname은 후보 허용목록에서 제거. 새 kllollain-max.github.io/careerpick 주소 사용. 이미 게시된 과거 문구/URL은 변경하지 않음.

## 실제 설정 확인

공식 Actions Secrets 화면에는 ALIO_KEY/DATA_GO_KR_KEY/GOJOBS_KEY/MPM_EXAM_KEY만 존재.
THREADS_ACCESS_TOKEN 및 THREADS_USER_ID 미등록. 비밀값을 읽거나 코드에 저장하지 않음.
사용자는 Settings → Secrets and variables → Actions → New repository secret에서 직접 등록해야 함. 채팅/파일로 토큰 전달 금지.

## 재개 차단 조건

게시 job은 schedule 이벤트와 THREADS_ENABLED=true 및 THREADS_MIGRATION_READY=true가 모두 필요.
workflow_dispatch는 실제 게시를 실행하지 않음. 과거 슬롯·rerun 자동 재게시 금지.
이전 publisher 상태와 최신 이력·미확정·중복을 대조하기 전 MIGRATION_READY를 켜지 않음.
원격 청구 branch는 threads-publisher-state. 기존 accepted 상태를 증거 없이 새로 만들어 복구 성공으로 보고하지 않음.

## 다음 실제 실행

1. 두 Secret 등록 후 Verify Threads migration without publishing을 read_meta=true로 1회 실행.
2. API에서 hid_119·이전 본문/답글 실제 존재·부모 연결 및 백업 이후 게시들을 대조. API GET 코드의 성공과 게시 권한 검증은 구분.
3. 기존 publisher의 실행 종료/접근 차단 상태와 원격 영수증을 확인. 최신 이력만 증거대로 병합하고 원본 백업 보존.
4. 원격 branch 접근·청구 영구 저장·게시 권한·단일 게시기 보장 후 두 운영 게이트 설정, 기존 ChatGPT 감시 예약만 대상 주소 변경 후 재개. 새 감시 예약 생성 금지.
5. 다음 정규 슬롯에서 accepted/본문/답글2/이력 일치를 확인. 시험 게시·누락분 보충 없음.

## 검증

관련 단위18개, YAML 구문, preview(no-send), 원본 이력 바이트 일치 확인. Meta 실제 조회·게시·원격 청구 쓰기·정규 운영 재개는 아직 미실행.
