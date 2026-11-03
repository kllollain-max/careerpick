## 현재 배포 상태 — 2026-11-03 16:15:32 KST

**공개 운영 주소: https://kllollain-max.github.io/careerpick/**

저장소는 public이며 GitHub Pages 수동 배포 [41593785022](https://github.com/kllollain-max/careerpick/actions/runs/41593785022)가 2026-11-03 16:04:08 KST에 성공했다. 워크플로 실행 main은 `13b5e59280411940fdd7cb73617aa397a2ac9a44`, 실제 빌드 원본은 `bee342c7c1db94e44172b47b78443540c7a34147`다. 후속 감사·문서 커밋은 공개 사이트를 자동으로 재배포하지 않는다.

실사이트 검색·상세 직접 접속 및 새로고침·저장 유지 검증을 통과했고 테스트 저장 항목은 제거했다. 공개 데이터 610개 목록·610개 상세 및 두 JSON의 SHA256이 보존 원본과 일치한다. 610건은 과거 보관 공고를 포함한다.

[이력 감사 41593953112](https://github.com/kllollain-max/careerpick/actions/runs/41593953112)는 테스트 8개, 커밋 36개·blob 1,332개 검사로 통과했다. 등록 키 4개와 고신뢰 패턴을 검사해 미해결 발견 0건이며, 정확한 과거 blob에서 확인한 모의 테스트 표지 3건은 따로 기록했다. [통합 증빙](https://github.com/kllollain-max/careerpick/blob/main/docs/evidence/public-release-20261103.json)을 남긴다.

정기 수집·원본 자동 반영·신규 GOJOBS/MPM API 운영 연동은 계속 보류한다.

## 필요한 이유

기존 커리어픽 접근 장애 후 새 저장소에서 검색·맞춤 조건·공고 저장·지원 관리 기능과 보존 데이터를 복원한다. PR #1은 병합됐으며, 사용자 승인에 따라 저장소 공개 전환과 GitHub Pages 최초 수동 배포를 완료했다.

## 변경 내용과 결과

- 기존 화면과 브라우저 저장 기능을 재사용하고 링크·canonical·PWA 범위를 `/careerpick/`로 조정했다. 계정 로그인이나 서버 동기화 기능이 복원됐다고 주장하지 않는다.
- 현재 데이터는 **610개 고유 공고**다. 기존 520건과 추가 복원한 90건을 보존하며, 수집 기준시각은 `2026-11-03T12:32:01+09:00`이다. 과거 공고를 포함한 수치다.
- ALIO OpenData(`ALIO_KEY`)와 공공데이터포털(`DATA_GO_KR_KEY`)의 목록·상세 API를 실제 인증해 검증했다.
- 수집 완전성, 정상 무변경 처리, 상세정보만 변경된 경우의 반영을 보완했다. 검증 실패 시 원본을 보존하며, 동일 결과에서는 기존 수집시각을 유지한다.
- 검토 원본 `review-workflows/deploy-pages.yml.disabled`와 같은 수동 배포 workflow를 `.github/workflows/deploy-pages.yml`에 활성화했다. 필수 `approved_sha` 검증과 정확한 SHA checkout·HEAD 대조, 고정 concurrency를 적용했다. 공개 허용목록으로 생성한 `dist/`만 업로드한다.

## 검증 근거

ALIO·기존 공공데이터포털 검증 코드 HEAD: `86548d2aa54191b10ff558368c29f940ba2446d9`. 해당 회차의 문서·증빙 커밋은 [`e2a55e3`](https://github.com/kllollain-max/careerpick/commit/e2a55e311312fd6fb580110dbcfa66b03146712c)이며 실행 코드와 데이터는 동일하다.

세 회차의 결과·원본 해시·공식 웹 관찰·검사 및 기존 UI 근거는 [통합 검증 기록](https://github.com/kllollain-max/careerpick/blob/e2a55e311312fd6fb580110dbcfa66b03146712c/docs/evidence/alio-followup-20261103.json)에 기록했다. 이번 세 실행의 증빙 범위는 실행 로그와 artifact 메타데이터다.

| 범위 | 결과·근거 |
|---|---|
| 기존 정적·화면 기능 | [41573700536](https://github.com/kllollain-max/careerpick/actions/runs/41573700536) 성공. 상세 27개·홈페이지 48개, 320/390/1440px 검색·상세 검증. 1,288개 출력 파일·30,141개 내부 링크, 누락 0. 해당 입력은 변경되지 않아 기존 근거를 재사용했다. |
| 이번 변경 대상 | unittest 41개와 기존 부분 수집 방어 검사가 로컬과 아래 GitHub 세 실행에서 모두 통과. ALIO 계약 3개·수집 16개·공공데이터 어댑터 12개·등록 검증기 4개·목록 부재 감사 6개. |
| ALIO 최신 실검증 | [41578577872](https://github.com/kllollain-max/careerpick/actions/runs/41578577872) 성공. 계약 3개·수집 16개·부분 수집 방어 검사 통과. 목록·상세·격리 수집 성공, 610 → 610, 추가·변경·삭제 0, 원본 및 12:32:01 기준시각 보존. |
| 공공데이터포털 최신 실검증 | [41578578108](https://github.com/kllollain-max/careerpick/actions/runs/41578578108) 성공. 13:31:14 KST 기준 509개 고유 목록, 목록 6회·상세 표본 3회, 첨부파일 정보 5개 확인. 610건 원본 보존. |
| 목록 부재 공고 감사 | [41578577992](https://github.com/kllollain-max/careerpick/actions/runs/41578577992) 성공. 검사 6개, 목록 6회·상세 4회. 상세 `no_data` 4건은 `unresolved`로 보존했고 비진행 확정 0건. |

## 추가 등록 API 후속 확인

이 후속 격리 실검증은 **2026-11-03 14:32:36 KST**, 코드 `e55c1a185e1abcbf1ee6ccd9162ac05c385b1467`에서 수행했다. [실행 기록](https://github.com/kllollain-max/careerpick/actions/runs/41584479030)과 [후속 증빙](https://github.com/kllollain-max/careerpick/blob/5f6b36b94b0d27a83443a8c1aeac0363ced9872b/docs/evidence/gojobs-followup-20261103.json)을 보존했다.

- **국가공무원 시험일정:** 인증 성공, 2026년 28개 단계별 행·시험명 10개·날짜 셀 107개 검증. 2027년 검증은 아니다.
- **나라일터:** 인증 성공을 보고서에 정확히 반영했다. 목록 2회·상세 2건 검증 후 ID `20`에서 `invalid_classification_pair`로 중단됐다. 실패 전 결과와 공고의 식별값을 보존한다.
- **실제 표본 범위:** `e01` 첫 페이지는 2008~2009년 공고 5건, `e02`는 0건이었다. 성공한 상세 ID `4`, `7`은 모두 `e01`이다. 최신 진행 공고 또는 경력경쟁 상세 검증으로 집계하지 않는다.
- **테스트 50개 통과**(GOJOBS 23·시험일정 16·공통 검증기 11). 실 API 실행은 분류 불일치로 **failure 유지**다. 엄격한 분류 기준과 비정상 종료를 유지했다.
- 기존 공고 **610 → 610**, 원본 JSON 두 파일의 바이트 보존. 새 API는 격리 확인 범위이며 기존 화면과 수집 데이터에 반영하지 않았다.

세부 결과는 [추가 API 연결 확인](https://github.com/kllollain-max/careerpick/blob/5f6b36b94b0d27a83443a8c1aeac0363ced9872b/docs/ADDITIONAL_API_CONNECTION_CHECK_20261103.md)에 정리했다.

## 남아 있는 확인 범위

진행 중 목록에서 빠진 101건 중 97건은 기존에 날짜가 지난 공고이고, 4건은 기한이 남아 있다. 후자의 상세 API는 `no_data`였으나 같은 날 직접 읽은 공식 웹페이지는 모두 진행 중·12월 31일 종료로 표시됐다. 목록 부재를 마감이나 삭제로 처리하지 않는다. 상세 검증은 표본 및 해당 부재 공고 범위이며, 전체 공고의 첨부파일 내용을 검수한 것은 아니다.

최신 문서·증빙 커밋: [`5f6b36b`](https://github.com/kllollain-max/careerpick/commit/5f6b36b94b0d27a83443a8c1aeac0363ced9872b). 실행 코드 검증 기준은 위에 명시한 커밋별로 구분한다.

## 현재 실행 범위

**저장소 공개 전환·PR #1 병합·Pages 설정·최초 수동 1회 배포는 승인받아 완료했다. 정기 수집·원본 자동 반영·신규 API 운영 반영은 계속 보류한다.**

비활성 수집 제안은 수동 후보 생성과 artifact 보관을 수행한다. 이를 정기 실행·원본 자동 반영·배포로 연결하는 운영 활성화는 별도 승인 범위다. 이전에 성공한 코드·화면 검증은 관련 입력이 바뀌지 않으면 재실행하지 않는다. 최초 공개 배포와 실사이트 검증 결과는 아래 완료 기록을 따른다.

## 나라일터 최근 자료 추가 확인 — 14:49 KST

[추가 실행 41586122438](https://github.com/kllollain-max/careerpick/actions/runs/41586122438)이 성공했다. 검증 코드 HEAD는 `fb6f9af62f7a64a34fb7c7ca1abd2bea2ed2f577`, 기록 커밋은 `c1f83826bfe23dba1b409c49496cf9bb6786d88e`다. [확인 범위와 결과](https://github.com/kllollain-max/careerpick/blob/c1f83826bfe23dba1b409c49496cf9bb6786d88e/docs/GOJOBS_CURRENT_SAMPLE_CHECK_20261103.md) · [두 추가 실행 증빙](https://github.com/kllollain-max/careerpick/blob/c1f83826bfe23dba1b409c49496cf9bb6786d88e/docs/evidence/gojobs-current-sample-20261103.json)

- 공식 페이지 번호 기능으로 공개경쟁 e01의 5,532페이지를 조회해 **2026-11-03 등록 ID 307403**의 목록·상세를 검증했다. 경력경쟁 e02는 첫 페이지 0건이다. 실제 페이지·총건수·남은 행 수를 확인했다.
- 해당 표본은 **대전 중구의회 최종합격자 발표·임용후보자 등록 안내**다. API 종료일 2026-11-13을 근거로 신규 지원자를 모집 중이라고 판정하지 않는다.
- 새 검사 **11개** 통과. 기존 코드의 **50개** 성공 근거는 재사용했다. 이번 마지막 페이지 실행은 나라일터 목록 2회·상세 1회, MPM 호출 0회이며 기존 **610건 원본 바이트를 보존**했다.
- 앞선 DESC 실험은 기존 첫 페이지와 같은 과거 5건 및 ID 20 분류 오류를 반환했다. 과거 오류를 성공으로 덮어쓰지 않으며, 정렬값의 공식 의미·최신순·전체 수집 완료를 주장하지 않는다.
- 기존 동시 반영 내용을 보존하고 별도 확인 스크립트·테스트·워크플로만 추가했다. 고정 페이지 진단이며 운영 수집기가 아니다. 이 14:49 KST 검증 당시에는 main 병합·배포·정기 수집을 수행하지 않았다. 이후 승인된 최초 공개 결과는 아래에 별도로 기록한다.


## 후속 분류 검사 확인

`bee342c7c1db94e44172b47b78443540c7a34147`의 `gojobs_notice_safety.py`와 새 테스트를 격리된 로컬 작업공간에서 실행했다. **11개 모두 통과**했다. 합격자 발표·시험 안내·미확인 접수 상태를 모집 중으로 오인하지 않는 오프라인 분류 검사다. 실제 운영 수집·화면 연결 완료를 의미하지 않는다. 기존 성공 API 호출 및 전체 UI 검사는 반복하지 않았으며 코드·데이터 변경은 없다. ALIO 610건과 기존 실패/미확인 증빙을 보존한다.

최초 공개 배포의 승인 원본 SHA는 `bee342c7c1db94e44172b47b78443540c7a34147`이며 실제 배포에서도 해당 커밋을 checkout했다. PR 병합·저장소 공개·Pages 설정·수동 1회 실행 및 실사이트 확인은 완료했다. 정기 수집·나라일터/시험일정 운영 화면 연결·블로그 변경은 이 범위에 포함되지 않는다.


## 승인 후 최초 공개 배포 완료 — 2026-11-03

사용자 최초 배포 진행 및 '저장소 공개 전환 승인'에 따라 PR #1을 병합(643bd425621dc1ca5fcb479aee09733a346049ea)하고 저장소를 public으로 전환했다. Pages 소스는 GitHub Actions, HTTPS 강제다. 수동 배포 workflow만 활성화했다.

실행 https://github.com/kllollain-max/careerpick/actions/runs/41593785022 / job 125776300749 success. 워크플로 실행 ref는 main(13b5e59), **실제 checkout·빌드·배포 코드는 승인 SHA bee342c7c1db94e44172b47b78443540c7a34147**이며 SHA 대조 단계와 로그에서 확인했다. ALIO 610건, dist 1,288개 파일, 내부 링크 누락 0, 원본 JSON 보존.

실제 URL https://kllollain-max.github.io/careerpick/ 접속 성공. 한국잡월드 검색 2건, 공고 저장 후 새로고침·저장 메뉴 1건 유지, 테스트 저장 해제 확인. /careerpick/jobs/a306130.html 직접 접속과 새로고침 성공. 상세 화면 가로 넘침·깨진 이미지 0, 관찰된 오류는 브라우저 확장 metadata 오류뿐이다. 전체공고 화면으로 복귀했다.

정기 수집 비활성 유지. 나라일터·시험일정 운영 화면 연동은 여전히 별도 후속 작업이다. 610건은 보관 공고를 포함하며 전부 모집 중이라는 뜻이 아니다. 기존 보류 문구는 이 승인 이전의 이력이며 위 범위만 승인·실행했다.
