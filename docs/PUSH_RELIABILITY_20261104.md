# 알림 신뢰성 점검 — 2026-11-04

로컬 검증: 2026-11-04 00:21 KST. main d09681bc14f9e737c183a9e4efceb2752d4fdc64 / 재사용 PR #11 기준 7e8831f761ad559e717ef807ac09207c4fb11321. 후속 브랜치는 PR #11을 base로 한다. 병합 후 최신 main에 재검증이 필요하다.

이번 실제 발송0건·실제 대상0명·구독변경0건. 병합·공개 배포·운영 변수 변경·차단 해제·네이버 접속 없음.

| 점검 항목 | 발견 문제·원인 | 수정 내용 | 검증 결과 | 남은 작업 |
|---|---|---|---|---|
| 실제 구독 상태 | SDK 필드 누락을 미등록으로 단정 | unknown·initializing·권한·등록·처리 상태 분리, 재조회 버튼, 화면 복귀 갱신 | Node 모의시험 통과 | 서버 대조·실기기 미검증 |
| 등록·ID 복사 | 권한 차단 후 optIn 재요청·맞춤 동기화 실패 무시 | 차단 시 설정 안내, 동기화 실패 명시. PR #11의 직렬화·수동복사 재사용 | 차단 시 optIn0회·중첩 호출1회 | OS 권한창·실제 클립보드 미검증 |
| 발송 대상·맞춤 조건 | 실행 경로 감사 | enabled·ID·cp_optin·packed profile 및 발송직전 lookup/matches 재검증 재사용 | 발송기 오프라인 검사 통과 | 실제 태그 미대조. 새 구독 ID의 사람 단위 중복/과거 backlog 수신 방지 정책 미완료 |
| 중복 방지·원장 | 공급자 idempotency_key 누락 | 요청당 UUIDv4, 429 재시도 동일 Request/키. 기존 CAS·accepted 보호·reserved/uncertain 차단 유지 | 발송기192개 통과 | 키는 요청 생명주기만 보존, 원격 원장 키 저장 미구현. crash 후 자동 재요청 금지 유지 |
| 실제 기기 수신 | 이번 실발송 없음 | API접수·수신 구분 유지 | 발송0·수신 미검증 | Android/iPhone/PWA 전경·배경·잠금·알림선택 미검증 |
| 해지·재구독 | !optedIn이 undefined/null도 성공 판정 | 명시적 false만 해지 확인. 권한 유지·접수된 알림 한계 안내 | 누락/오타입/getter 오류 성공 거부 | 서버 반영·재구독 ID변경 실검증 남음 |
| 장애·복구 | SDK 오류 상태·종료 타이머 잔존 | 확인 불가·재조회, timeout 타이머 정리. 기존 세대 보호/재로드 재사용 | 모의시험 통과 | 실제 SW충돌·원격장애·차단원인 미검증 |

## 현재 실행 경로·설정 근거

- index.html → OneSignal v16 / push-config.js / onesignal/OneSignalSDKWorker.js. 빌드가 /careerpick/ 경로 적용.
- targeted-push.yml → run_targeted_push → detect_new_job_alerts → send_all_opted_in_bounded → guarded transport. 자연 예약수집 성공 후만 자동 진입, 수동은 check/initialize. concurrency careerpick-targeted-push, 회차100명 조회·3건 제한 유지.
- private GitHub Contents CAS 원장·queue·circuit·baseline. seen ID 합집합 보존 및 최초 소급0. 이번 원격 원장 읽기/쓰기 없음.
- 필수 이름: CP_ONESIGNAL_REST_API_KEY, CP_LEDGER_REPOSITORY, CP_LEDGER_TOKEN. 운영변수 CP_ENABLE_ALL_OPTED_IN_ROLLOUT, workflow가 CP_ENABLE_LIVE_PUSH를 주입한다. 비밀값 출력 없음.
- 최신 확인한 운영 실행 https://github.com/kllollain-max/careerpick/actions/runs/41643065384 : 2026-11-03 22:17:45 KST, main d09681b, failure. job125941208689 오프라인191 성공 후 운영 단계 blocked / error_type Blocked / missing_secrets []로 중단. 해당 시각 세 값이 비어있지 않았다는 근거이며 현재 등록·권한·유효성 전체 검증은 아니다. 차단 세부 원인은 공개 로그에 없어 추정하지 않으며 해제하지 않았다. 이 실행의 발송 수·수신은 미확인.
- check/initialize 실행41621747324·41621955756 success는 실발송 성공 증거로 사용하지 않는다.
- 현재 Secrets 등록 목록·운영변수 값·비공개 원장·OneSignal 대시보드·구주소 발송기 종료는 도구 읽기 범위로 미확인. 이전 구독 자동이전·이전 시스템 종료를 완료로 보고하지 않는다.

## 검증·제약

새 Node7 포함 관련 Node69 통과. VM은 실브라우저가 아니다. 네트워크 소켓 차단 발송기192 통과, 기존 대규모 스트레스2 제외. 반복·동시 CAS·해지 제외·응답유실·접수 후 저장실패·baseline·불확정 차단 검사 포함. 별도 Chromium CI는 PR에 결과를 기록한다.

정적 빌드 HTML1,277 / 내부링크30,650 / 누락0 / 원본JSON보존 / 수집0 / 배포0.

SDK optedIn/id/token은 로컬 등록 증거이고 실제 서버 처리·기기 수신 증거가 아니다. getTags는 SDK 조회이며 REST 서버 대조와 구분한다. UUID 보호는 30일이며 수신보장이 아니다. 영구중복 보호는 원장 담당. 새 키가 uncertain 재발송 허가가 되지 않는다.

현 발송은 ALIO 신규채용. 정정/연장·GOJOBS·D-1 신규 구현은 하지 않았다. 다른 출처·종류 추가 시 source+ID+target+kind+version을 별도 설계해야 한다.

## 승인 후 실기기 확인

한 기기/시험 구독 별도 승인 후: 새 주소 권한·등록·조건 확인 → 단건 대상선정 → 요청/notification ID 비공개보존 → 서비스 상태 → OS/브라우저/전경·배경·잠금별 수신시각 → 알림선택 공고 일치 → 해지 후 제외 → 재구독 이력정책 확인. 사용자 기기 수신은 사용자 확인 필요. API성공만으로 수신성공 처리하지 않는다.

공식 구현 근거: https://documentation.onesignal.com/reference/idempotent-notification-requests 및 https://documentation.onesignal.com/docs/en/web-sdk-reference (2026-11-04 확인).
