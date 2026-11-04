# 지원금픽 사이트 운영·복구 준비

## 승인 요청 대상

- 새 공개 저장소 후보: `kllollain-max/supportpick` (2026-11-04 확인 시 아직 없음).
- 예정 주소: `https://kllollain-max.github.io/supportpick/`. 아직 공개한 주소가 아니다.
- 코드 검토: careerpick Draft PR #16, `codex/supportpick-site-20261104`. 기존 커리어픽 main에는 병합하지 않고 검증된 지원금픽 폴더만 새 저장소로 이전한다.
- 실제 수집 검증: automation-system Draft PR #9, 수동 검증 실행 41774386414. 기존 블로그 PR #8과 운영 예약은 변경하지 않는다. PR #9도 검증 전용이며 기존 저장소 main에 병합할 필요가 없다.
- 새 저장소 생성·검증본 이전·해당 저장소 검토 PR 병합·Pages 배포·전용 Secrets 등록 및 아래 두 운영 변수 활성화를 한 범위로 승인받는다. 승인 전 실제 변경은 없다.

## 실제 자료와 비용 근거

2026-11-04 13:38:10~13:45:39 KST, 목록·상세·지원조건 각 110페이지에서 각 10,942건을 받았다. 보고 총건수=수신=고유 ID=저장 10,942, 중복 0, 표본 0이다. 세 endpoint ID 집합이 일치했고 각 첫 페이지를 수집 후 다시 조회해 경계 값·총건수가 유지됨을 확인했다. API가 트랜잭션 스냅샷 토큰을 제공하지 않아 모든 행이 동일한 한 시점의 값임을 보장하지는 않는다.

실제 호출은 333회: 110×3 페이지 + 경계 재확인 3회. 정상 기준 1일 2회는 약666회/일이다. 일시 오류에는 요청당1회만 재시도하고 인증·권한·429는 즉시 중단한다. 실행당 하드 상한800회, 일일 두 회차 상한1,600회다. 간격은 최소0.35초이며 소스 변화·누락·중복·10% 초과 급감은 정상 자료 교체를 차단한다.

공식 포털은 무료, 이용허락범위 제한 없음, 개발계정 신청 가능 트래픽10,000을 안내한다. 이는 개별 계정의 실제 할당량·만료일 확인을 대신하지 않는다. 해당 두 계정 값은 로그인 필요로 미확인이며, 정기 활성화 승인 전 확인 대상이다. 공식 확인 출처:

- https://www.data.go.kr/data/15113968/openapi.do?recommendDataYn=Y
- https://infuser.odcloud.kr/api/stages/44436/api-docs

승인 제안 주기는 **06:20·18:20 KST**, cron `20 9,21 * * *`(UTC)다. GitHub 예약 실행은 지연될 수 있으며 정각 실행을 보장하지 않는다.

## 전용 설정

| 이름 | 위치 | 용도 |
|---|---|---|
| `SUPPORTPICK_GOV24_SERVICE_KEY` | 새 저장소 Actions Secret | 승인된 보조금24 키. 기존 저장소 키를 로그·공개 파일로 내보내지 말고 소유자가 비밀 설정으로 등록 |
| `SUPPORTPICK_SITE_COLLECTION_APPROVED=1` | 새 저장소 Actions Variable | 정기 수집 허용 |
| `SUPPORTPICK_SITE_PUBLIC_UPDATE_APPROVED=1` | 새 저장소 Actions Variable | 정상 자료 또는 실패 상태를 Pages에 반영하도록 허용 |
| `github-pages` | 새 저장소 Environment | Pages 배포 대상 |

현재 workflow는 `workflows/*.yml.disabled`에만 있다. 승인 후 새 저장소 `.github/workflows/`에 복사한다. 작업 중 새 정기 예약·변수 변경·기존 배포 변경은 없다.

## 설치·빌드

제공한 배포 준비 ZIP의 `source/`를 새 저장소 루트로 사용한다. **`bootstrap-state.zip`과 `bootstrap.json`도 함께 포함**한다. 코드 PR은 대용량 데이터 대신 이 초기 데이터의 해시와 복구 코드를 기록하며, 실제 초기 자료는 배포 준비 패키지에 포함된다. `collection-state/`는 원본 ZIP에서 무결성 검사 후 복원되는 실행 상태라 Git 이력에는 넣지 않는다.

```sh
python3 tools/bootstrap_state.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/core.test.cjs
python3 tools/build.py --output dist
```

일반 빌드는 미리보기 noindex를 유지한다. 공개 승인 후에는 아래 명령이 지정 프로젝트의 canonical과 index 정책을 생성한다. 파일경로는 상대 경로이며 `/supportpick/`에서 동작한다.

```sh
python3 tools/build.py --output dist --public-base https://kllollain-max.github.io/supportpick/
```

출력은 HTML/CSS/JS·공식 자료·상태·버전별 상세 조각과 사이트 manifest만 포함한다. 키·원본 API 페이지·수집/복구 도구·문서·검사는 공개하지 않는다. 정상 자료 시 공개 파일45개, 약48MB이며 첫 목록은30개씩 표시하고 상세는 선택 시 해당 조각만 읽는다. 연락처·금액 등은 공식 API 원문이며 전수 사실검수·링크 HTTP 전수 확인과는 다르다.

## 자동 갱신과 장애 재개

정기 workflow는 신뢰한 main 운영 회차의 최신 상태 artifact를 복원하고 manifest·현재 포인터를 검사한다. 없으면 배포 패키지의 초기 정상 자료를 사용한다. 새 데이터는 독립 회차 폴더에 저장하며 페이지별 JSON·해시·수신시각·체크포인트를 보존한다. 검증이 끝난 세대 폴더를 먼저 완성한 뒤 `current.json` 포인터를 원자적으로 교체한다. 실패 시 포인터와 마지막 성공 시각을 유지하고 `status.json`만 실패로 기록한다.

한 회차의 통신 실패는 보존된 `output/current-run/`을 복원해 **같은 generation·같은 output 경로**로 `collect_full.py`를 재실행하면 완료 페이지를 재사용한다. 체크포인트 변조·원본 변경·ID 불일치라면 같은 자료를 무조건 재시도하지 않고 원인을 확인한 뒤 새 generation에서 시작한다. 검증 미완료 후보는 운영 포인터로 승격하지 않는다.

`supportpick-runtime-state`와 수집 증거 artifact는14일 보존하며, 항상 초기 정상 자료의 bootstrap도 코드와 함께 유지한다. 장기간 중단 뒤 최신 artifact가 만료되면 오래된 초기 자료로 복원됐음을 수집 시각·지연 안내로 드러낸다. 과거 자료를 최신으로 표시하지 않는다.

## 복구

1. 배포 준비 ZIP의 파일 manifest·SHA-256·ZIP CRC를 확인한다.
2. 새 작업 폴더에 `source/`를 복원하고 bootstrap 해시와 세대 manifest를 검사한다. 키는 위 Secret 이름으로만 재등록한다.
3. 이전 정상 세대로 되돌릴 때는 보존된 정상 상태 artifact를 별도 폴더에 먼저 풀고 `tools/refresh.py`의 `read_current()`로 모든 파일 해시·ID·건수를 확인한 후 포인터를 교체한다. 마지막 성공 시각을 현재로 쓰지 않는다.
4. 빌드 후 검증하고, 배포 승인 범위에서만 Pages 아티팩트를 게시한다. 기존 커리어픽·블로그·웹푸시 설정은 건드리지 않는다.

사용자 개인 기록은 브라우저의 `supportpick:*` 키에 있으며 JSON 또는 텍스트 백업으로 복원한다. 커리어픽의 `saved/apps/prefs/spec`를 읽거나 쓰지 않는다. 새 서비스워커·푸시·분석 스크립트는 등록하지 않는다.

## 승인 후 운영 검증

정확한 승인 소스·배포 SHA를 기록하고 수동1회 수집 성공, 공개 주소의 실제 목록·상세·저장, 이후 실제 예약2회 연속 성공을 각각 확인한다. 아직 예약 실행은0회이며 자동 운영 검증 완료가 아니다.
