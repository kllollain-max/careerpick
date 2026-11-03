# CareerPick 복구 인수인계 — 2026-11-03

## 현재 상태

- 저장소: `kllollain-max/careerpick`; PR **#1은 2026-11-03 06:49:34 UTC에 병합됐다**. 병합 커밋은 `643bd425621dc1ca5fcb479aee09733a346049ea`다.
- 작업 브랜치: `codex/restore-careerpick-20261103`.
- ALIO·기존 공공데이터포털 검증 코드: `86548d2aa54191b10ff558368c29f940ba2446d9`. 추가 API 보고기 검증 코드는 `e55c1a185e1abcbf1ee6ccd9162ac05c385b1467`다. 이후 문서·증빙 커밋과 실행 코드 변경을 구분한다.
- 배포 준비 확인 시 main은 `d4d9681a935aa899a5605e5ae1ed7c803c795966`이며, `.github/workflows/deploy-pages.yml`이 검토 원본과 동일한 내용으로 활성화됐다. 배포 당시 main 커밋은 `13b5e59280411940fdd7cb73617aa397a2ac9a44`에 기록한다.
- 현재 원본 스냅샷: **610개 고유 공고**, 수집 기준시각 `2026-11-03T12:32:01+09:00`. 과거 520건과 새로 복원한 90건을 함께 보존한다. 610건 모두를 현재 모집 중인 공고로 표현하지 않는다.
- 대상 주소: `https://kllollain-max.github.io/careerpick/`. 저장소는 public으로 전환됐고 승인된 수동 Pages 배포가 성공했다. 실제 확인 결과는 아래에 기록한다.

## 최초 공개 결과 기록

2026-11-03 사용자는 무료 운영을 위해 **저장소 공개 전환·PR #1 병합·Pages 설정·수동 1회 배포**를 승인했다. 정기 수집·원본 자동 반영·신규 GOJOBS/MPM API의 운영 반영은 계속 보류한다.

| 기록 항목 | 실제 결과 |
|---|---|
| 기록 시각(KST) | `2026-11-03 16:15:32 KST` |
| 저장소 공개 상태 | `public` |
| 배포 당시 main 커밋 | `13b5e59280411940fdd7cb73617aa397a2ac9a44` |
| Pages 설정 | `GitHub Actions; HTTPS site enabled` |
| 승인된 배포 원본 SHA | `bee342c7c1db94e44172b47b78443540c7a34147` |
| 배포 실행 | `https://github.com/kllollain-max/careerpick/actions/runs/41593785022` |
| 배포 결과 | `success — 2026-11-03 16:04:08 KST` |
| 실사이트 루트·상세 직접 접속·자산·브라우저 저장 확인 | `PASS: root rendering; 한국잡월드 search returned 2 results; saved notice persisted across detail navigation and root return; test save removed (0 remaining); /careerpick/jobs/a306130.html direct open and refresh; sampled assets/data HTTP 200.` |

실제 배포 SHA와 문서·감사 후속 커밋을 구분한다. main의 후속 변경은 수동 배포를 다시 실행하지 않는 한 공개 사이트에 자동 반영되지 않는다.

## API·수집 검증 완료

두 서비스의 키와 호출 경로를 분리한다. 키 값은 읽기·출력·커밋하지 않는다.

| 경로 | Secret | 검증 근거 |
|---|---|---|
| ALIO OpenData POST 목록·상세 | `ALIO_KEY` | [41578577872](https://github.com/kllollain-max/careerpick/actions/runs/41578577872), success |
| 공공데이터포털 GET 목록·상세 | `DATA_GO_KR_KEY` | [41578578108](https://github.com/kllollain-max/careerpick/actions/runs/41578578108), success |

- ALIO: 목록·상세 및 격리 수집 성공. **610 → 610, 추가 0·변경 0·삭제 0**, 원본 보존. 정상 무변경 시 원본 수집시각 12:32:01을 유지했다. CI에서 계약 검사 3개, 수집 검사 16개와 기존 부분 수집 방어 검사가 통과했다.
- 공공데이터포털: 13:31:14 KST 기준 **509개 고유 공고**, 목록 6회·상세 표본 3회 성공. 첨부파일 정보 5개와 원본 `steps` 값을 확인했다. 비교 결과는 동일한 610건이며 원본을 변경하지 않았다. 상세·첨부 내용의 전수 검수로 확대해 표현하지 않는다.
- 수집기는 완전성 검증, 정상 무변경과 실패 구분, 상세정보만 변경된 경우의 반영을 보완했다. 대상 unittest 41개와 기존 부분 수집 방어 스크립트가 로컬과 GitHub의 세 실행에서 모두 통과했다. 41개는 ALIO 계약 3개·수집 16개·공공데이터 어댑터 12개·등록 검증기 4개·목록 부재 감사 6개의 합계다.
- 현재 API 등록·실인증 차단 요소는 해결됐다. 인증키 재등록이나 이전 실패 회차의 무조건 재실행을 요구하지 않는다.

## 추가 등록 API의 최신 상태

- `MPM_EXAM_KEY`: 2026년 연간 시험일정 28개 단계별 행·시험명 10개 검증. 2027년이나 모든 변경 공지를 확인한 결과가 아니다.
- `GOJOBS_KEY`: 실제 인증 확인. 목록 2회와 상세 2건은 검증됐고, 세 번째 상세 ID `20`은 분류 불일치로 거부됐다. 성공한 결과와 실패 ID를 보존하며 전체 검증 실패는 유지한다.
- 이번 `e01` 첫 페이지는 2008~2009년 공고 5건, `e02`는 0건이다. 상세 ID `4`, `7`도 모두 `e01`이므로 최신 진행 채용이나 경력경쟁 상세 확인으로 보고하지 않는다.
- 14:32 KST 실행 [41584479030](https://github.com/kllollain-max/careerpick/actions/runs/41584479030): 테스트 50개(23+16+11) 통과, 실 API 검증 failure. 기존 610건 원본은 바이트 단위로 보존됐다.
- `docs/evidence/gojobs-followup-20261103.json`과 `docs/ADDITIONAL_API_CONNECTION_CHECK_20261103.md`를 기준으로 인수인계한다. 이전의 실패 ID 미확인·인증 false 표시보다 이 후속 결과가 우선한다.
- 새 API의 운영 수집·화면 적용은 미구현이다. 정렬 순서를 추정하거나 원본 분류 불일치를 정상으로 받아들이지 않는다. 같은 입력을 무조건 재실행하지 않는다.

### 14:49 KST 최근 자료 확인

[41586122438](https://github.com/kllollain-max/careerpick/actions/runs/41586122438)은 코드 `fb6f9af62f7a64a34fb7c7ca1abd2bea2ed2f577`에서 성공했다. e01 마지막 페이지에서 2026-11-03 등록 ID 307403의 목록·상세를 확인했다. 이는 대전 중구의회 최종합격자 발표·임용후보자 등록 안내이며 신규 지원자를 모집 중인 공고로 판정하지 않는다. e02 첫 페이지는 0건, MPM 호출은 0회다. 새 검사 11개가 통과했고 610건 원본 바이트를 보존했다. ID 20의 앞선 분류 오류는 별도 실패 기록으로 유지한다. 이 확인은 고정 페이지 진단이며 운영 수집기가 아니다.

## 진행 중 목록에서 빠진 공고 처리

통합 증빙: `docs/evidence/alio-followup-20261103.json`. 최신 세 회차의 실행 결과·원본 해시·공식 웹 관찰·41개 대상 검사와 재사용 UI 근거를 함께 읽는다. 이번 세 실행의 증빙 범위는 실행 로그와 artifact 메타데이터다.

[41578577992](https://github.com/kllollain-max/careerpick/actions/runs/41578577992)는 상태 감사 검사 6개와 실제 목록 6회·상세 4회로 성공했다.

- 보존 공고 중 목록 부재는 101건: 이미 날짜가 지난 97건과 기한이 남은 4건.
- 기한이 남은 4건의 상세 API 결과는 모두 `no_data`이며 상태는 `unresolved`로 유지했다. **공식 비진행으로 확정한 건수는 0**이다.
- 같은 날 공식 웹페이지를 직접 읽은 결과 4건 모두 `진행중`, 종료일 12월 31일로 표시됐다. 해당 URL·확인일은 최종 상태 증빙과 함께 유지한다.
- 목록 부재 또는 상세 `no_data`만으로 마감·삭제하지 않는다. 4건을 유지하고 확인된 근거만 상태 판정에 사용한다.

## 운영 상태와 후속 범위

- 기존 정적/UI 근거 [41573700536](https://github.com/kllollain-max/careerpick/actions/runs/41573700536)를 재사용한다. 정적/UI 입력과 스냅샷은 이번 수집 코드 수정으로 변경되지 않았다: 1,288개 출력 파일, 내부 링크 30,141개 확인·누락 0, 상세 27개·홈페이지 48개 검사, Chromium 320/390/1440px 검사 통과. 새 수집 코드의 검증과 구분해 보고한다.
- `review-workflows/deploy-pages.yml.disabled`는 검토 원본이며, 동일한 내용의 `.github/workflows/deploy-pages.yml`이 활성화됐다. 수동 실행만 허용하고 필수 `approved_sha` 40자리 검증, 정확한 SHA checkout, 실제 HEAD 대조, 고정 concurrency를 적용한다. 빌드 허용목록을 거친 `dist/`만 배포 대상으로 삼는다.
- 최신 사용자 승인에 따라 **저장소 공개 전환·PR 병합·Pages 설정·최초 수동 1회 배포**가 완료됐다. **정기 수집·원본 자동 반영·신규 GOJOBS/MPM API 운영 반영 보류**는 유지한다.
- 필요한 코드·데이터 정합성 수정과 문서·증빙 정리는 이어갈 수 있다. 관련 입력이 변경되지 않은 UI 검사나 성공한 인증 호출은 반복하지 않는다.
- `review-workflows/collect-alio.yml.disabled`는 수동으로 후보 데이터를 생성해 artifact로 보관하는 제안이다. 정기 실행·원본 자동 반영·배포를 연결한 운영 시스템은 아직 활성화되지 않았다.
- 승인된 최초 배포는 위 원본 커밋으로 완료됐고 성공 결과를 기록했다. 정기 수집·원본 반영·자동 배포 연결은 별도 운영 범위이며, 격리 검증 성공만으로 활성화됐다고 보고하지 않는다.
- 사용자는 무료 운영을 위한 공개 저장소 Pages 방식을 승인했다. 실제 저장소 공개 상태·Pages 설정·배포 결과는 위 기록을 따른다. [공식 지원 범위](https://docs.github.com/en/pages/getting-started-with-github-pages)
- 최초 1회 배포 승인 범위에는 PR 병합, `.github/workflows/deploy-pages.yml` 활성화, Pages의 GitHub Actions 소스 설정, `approval=DEPLOY_CAREERPICK`·`approved_sha`를 지정한 수동 실행이 포함된다. PR 병합과 워크플로의 기본 브랜치 반영은 확인됐다. [공식 실행 조건](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- 실사이트 루트·상세·자산·저장 검증 결과를 위 기록과 증빙에서 확인한다. 블로그·Threads·다른 저장소의 예약과 설정은 건드리지 않는다.

## 공개 배포·이력 검사 증빙

통합 기록: `docs/evidence/public-release-20261103.json`. 배포 실행은 [41593785022](https://github.com/kllollain-max/careerpick/actions/runs/41593785022), 실행 ref는 main `13b5e59`, 실제 checkout·빌드 원본은 승인된 `bee342c`다. 빌드 보고서의 `deployed=false`는 빌드 단계의 값이며 그 뒤 Pages 배포 단계가 16:04:08 KST에 성공했다.

이력 감사 [41593953112](https://github.com/kllollain-max/careerpick/actions/runs/41593953112)는 `47c464ec34078d06816a18818262cb3eb0eb1d90`에서 성공했다. 테스트 8개, 도달 가능한 커밋 36개·blob 1,332개·24,578,218바이트를 검사했다. 등록된 키 네 개를 runner 내부에서 비교했고 미해결 발견은 0건이다. 처음 검사에서 탐지된 모의 테스트 표지 3건은 정확한 blob SHA·경로를 검토해 별도로 기록했다. 값은 출력하거나 커밋하지 않았다.

공개 HTTP 표본 7개가 모두 200이며 두 데이터 JSON의 SHA256은 보존 원본과 같다. 목록 610개·고유 ID 610개·상세 610개·수집 기준시각 일치를 확인했다. 관련 입력이 바뀌지 않으면 성공한 API/UI/HTTP 검사를 반복하지 않는다.
