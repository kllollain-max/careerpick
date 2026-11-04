# 커리어픽 Google·네이버 검색 점검

## 1. 결론

**코드 정비·오프라인 검증 완료 / 공개 반영·검색 도구 소유확인 필요.** 검색 순위·색인 성공·반영 시점은 보장하지 않는다. 검색 도구 등록, 검색 색인, AdSense 사이트 승인은 서로 다른 상태다.

대상은 `kllollain-max/careerpick` 및 `https://kllollain-max.github.io/careerpick/`이다. 기존 Draft PR #17에 검색 접근성 보완을 이어 붙인다. main 병합·공개 배포·검색 도구 등록·소유확인·사이트맵 제출은 이번 점검에서 실행하지 않았다.

## 2. 확인 기준

- 조회한 main: `c09f54b932da923148da52365d6084ca83eaabee`.
- 착수 시 작업 브랜치: `4f5e4156e497c072abf0b814dab282e3114ce769`. 본 문서를 포함한 후속 작업 SHA와 CI 결과는 PR #17의 최신 head에서 확인한다.
- main과의 차이 중 최신 Threads 이미지·게시 이력 2개는 원래 blob을 그대로 보존해 작업 브랜치에 반영한다. 운영 설정을 바꾸지 않는다.
- 공개 URL 검사: 2026-11-04 18:57 KST. 홈페이지·사이트맵·가이드 목록/대표 글·대표 공고·소개·개인정보·문의 8개 경로 HTTP 200. 호스트 루트와 루트 robots.txt는 404. 상세 응답·해시는 `docs/evidence/search-live-20261104.json` 참조.
- 공개 홈페이지의 canonical은 이미 `/careerpick/`와 일치했다. 이 항목은 재개발하지 않았다. 반면 초기 HTML의 내부 공고 상세 링크는 공개본에서도 0개로 재현했다.
- 공개 배포의 코드/자료 식별은 기존 `adsense-live-followup-20261104.json`과 구분한다. 로컬 `build-report.json`의 source_commit은 동기화 전 로컬 Git HEAD이므로 수정 파일의 커밋 증거로 사용하지 않는다. 원격 CI의 checkout/PR merge SHA를 사용한다.

## 3. 기준의 구분

| 구분 | 점검 및 처리 |
| --- | --- |
| 검색 접근의 기본 조건 | 로그인·클릭·알림 허용 없이 본문과 표준 HTML 링크를 제공하고 공개 URL이 응답하는지 확인 |
| 조건부 요건 | JobPosting을 제공할 때 실제 단일 공고 본문·모집 상태·마감과 일치해야 함. 보관 자료의 미확인 마크업을 제거하고 본문/URL은 보존 |
| 권장 개선 | 절대 canonical·일관된 내부 링크·사이트맵·구별되는 제목/설명·정확한 수정일. 사이트맵/검색 도구 등록 자체는 검색 노출의 보장이나 AdSense 승인 필수조건이 아님 |
| 계정 확인 필요 | Google Search Console·네이버 서치어드바이저 실제 소유확인 코드, 등록 범위, 제출 결과, 색인/실적 리포트 |

루트 robots.txt 부재를 수집 차단으로 판단하지 않는다. `/careerpick/robots.txt`가 200이어도 호스트 루트 규칙을 대신하지 않는다. 다른 프로젝트의 루트 설정은 변경하지 않는다. Googlebot/Yeti 문자열로 보낸 일반 HTTP 요청은 동일 본문/200을 받았지만 실제 검색봇 IP의 방문·색인 증거는 아니다.

## 4. 수정 결과

| 파일 | 이전 → 이후 |
| --- | --- |
| `sitegen.py` | 정적 목록이 외부 원문으로만 연결 → 실제 생성된 ALIO 상세 HTML로 연결. 누락/잘못된 ID는 기존 원문 대안 유지 |
| `scripts/build_public_site.py` | 홈페이지 생성 후 상세 생성 → 상세를 먼저 생성하여 신규 수집 ID도 첫 HTML에서 연결. 기존 공개 파일 허용목록/자료 보존 유지 |
| `sitegen.py`, `scripts/build_sitemap.py` | 재빌드 날짜를 모든 URL의 lastmod로 기록 → 검증된 영속 수정 시각이 없으므로 선택 항목 lastmod 생략 |
| `scripts/search_readiness.py` | 상세 제목/설명 중복을 기존 공고 ID로 구별. 본문·공식 출처·canonical·개인 기록은 유지. 보관 공고의 미확인 standalone JobPosting만 제거 |
| `kofpi.html` | 연결 도구의 설명/H1 누락 → 목적을 설명하는 제목과 요약 추가. 기존 POST 연결 동작 유지 |
| `tests/test_search_readiness.py`, PR 검사 workflow | 새 회귀 9개, 전체 생성본의 대표 주소·사이트맵·제목/설명·만료 마크업 검사 추가. 실패 시 PR 검사 실패, 검색 보고서를 검토 아티팩트로 제공 |

신규 공고/가이드 페이지를 양산하거나 기존 보관 공고를 삭제하지 않았다. `kakao.html`의 기존 noindex와 사이트맵 제외는 이미 정상이라 유지했다. noindex를 새로 추가해 심사를 우회하지 않았다.

## 5. 콘텐츠 검토와 남은 가치 보완

기존 가이드 6편과 정적 상세 939개를 재사용했다. 이번 변경은 검색 발견성과 정보 표현 정비다. 공고 ID를 붙여 메타데이터 중복을 구별해도 본문의 독창성·충실성이 자동으로 해결되지는 않는다.

현재 ALIO 665건은 지원자격/전형 절차가 있지만 별도 실제 담당업무 설명은 없다. 공식 첨부 공고를 근거로 사람이 선별·검토할 내용은 기존 콘텐츠 확인표에 남긴다. 실제 접수기간과 ALIO 게시기간을 동일시하지 않는다. 보관 274개는 안내 문구와 본문을 보존한다.

기존 JobPosting 중 만료 1개와 나머지 보관 공고의 미확인 마크업 6개를 생성 산출물에서 제거했다. 현재 생성본 JobPosting은 0개다. 일반 HTML 검색 대상은 유지하며, 채용 리치 결과 준비 완료로 보고하지 않는다. 충분한 직무 설명과 확인된 접수기간을 확보할 때 해당 공고만 다시 검토한다.

## 6. 검증과 재현

- 이번 로컬 실행: Python 27+5+26+9, Node 54 = **121개 통과**. 기존 기록/가져오기·맞춤 저장 오류 보호 검사를 포함한다. 변경 후 원격 CI 결과는 PR에서 별도 확인한다.
- 상세 생성기 self-test, 사이트맵 추가·보존·삭제·재실행 안정성 검사 통과.
- 새 생성본: HTML 1,312개, 내부 링크 32,396개, 사이트맵 URL 1,308개, 누락 링크 0개. 홈페이지 정적 내부 공고 링크 40개, 제목/설명 중복 그룹 0개, canonical/사이트맵 오류 0개, 경고 0개. 입력 JSON 7종의 바이트 해시 불변.
- 본문·마감 사실을 이 검사만으로 사람이 검토했다고 표시하지 않는다.
- 브라우저: 스크립트/외부 SDK를 차단한 홈페이지·대표 공고를 각각 320/390/1440px iframe에서 확인. 실제 문서 폭 305/375/1425px(스크롤바 제외), 가로 넘침 0. 공고 상세 직접 방문·새로고침 뒤 H1 및 공식 원문 링크 2개 유지. 실제 휴대전화/운영 SDK 실패/전체 검색 UI 수동 회귀와는 구분한다.

```bash
python -m unittest discover -s tests -p test_search_readiness.py
python scripts/build_public_site.py
python scripts/search_readiness.py
```

빌드는 허용된 공개 스냅샷만 읽고 dist를 생성하며 네트워크 수집·발송·배포하지 않는다. 검색 검사는 `build-search-report.json`을 작성한다. 공개 robots/응답 확인은 별도 읽기 검사이며 도구의 실패를 사이트 장애나 검색봇 차단으로 해석하지 않는다.

## 7. 광고와 검색의 분리

실제 광고 요청은 비활성 상태다. 가이드 후보·개인 관리/빈/오류 화면 제외 운영안은 기존 PR 문서를 유지한다. 이번 검색 정비로 자동 광고·검증 코드·통계 SDK를 켜지 않았다. 광고 검증·사이트 승인·검색 색인·순위는 각기 별도 결과다.

## 8. 검토 자료와 이후 순서

- Draft PR: https://github.com/kllollain-max/careerpick/pull/17
- 공개/생성본 증거: `docs/evidence/search-live-20261104.json`, `docs/evidence/search-offline-20261104.json` 및 CI의 `build-search-report.json`.
- 미리보기는 로컬 검증용으로만 열었으며 공개하지 않았다. 루트 배포 후보는 `review-only/host-root/`에 남겨 별도 승인 전 공개하지 않는다.
- 미병합 철회는 Draft PR 닫기. 적용 후 되돌림은 최신 수집자료·개인 기록을 보존하는 revert 커밋으로 준비한다. 저장공간 초기화/이전·도메인 변경 불필요.

승인 후 변경 SHA를 병합·공개 배포하고 먼저 공개 URL/정적 링크/사이트맵을 재검증한다. 이후 실제 계정에서 소유확인 및 사이트맵 제출, 대표 홈페이지·가이드·상세의 색인 진단을 순서대로 수행한다. 일괄 반복 색인 요청은 하지 않는다.

## 9. 사용자 확인 최소 항목

| 항목 | 현재 상태와 다음 작업 |
| --- | --- |
| Google Search Console | 앞선 선택 계정 읽기 확인에서 새 CareerPick 속성 없음. URL 접두사 `https://kllollain-max.github.io/careerpick/`를 후보로 준비. DNS 권한 없이 가능한 HTML 태그/파일 방식의 실제 발급값을 사용하며 임의 토큰을 넣지 않음 |
| 네이버 서치어드바이저 | 사용자는 미등록이라고 알려줌. 이번에는 계정 화면에 접속하지 않았음. 실제 등록 화면의 호스트/경로 허용 범위와 발급값 확인 필요. Google의 경로 속성 규칙을 네이버에도 그대로 적용하지 않음. 호스트 단위가 요구되면 루트 페이지/태그의 별도 공개 승인 필요 |
| 사이트맵 | 두 도구에 제출할 후보는 `https://kllollain-max.github.io/careerpick/sitemap.xml`. 실제 소유 범위가 포함하는지 확인 후 제출 |
| 공개 변경 승인 | PR #17의 검색/기존 개인정보·콘텐츠 보완 범위를 함께 검토. 기존 운영자 콘텐츠 확인·개인정보 보유/처리 근거 미결은 검색 검사로 완료 처리하지 않음 |

사이트맵·소유확인은 권장 운영 도구다. 미등록 자체를 검색 차단 또는 AdSense 불승인으로 단정하지 않는다. 승인 없는 공개 변경·계정 등록·제출은 수행하지 않는다.

## 공식 근거 (2026-11-04 확인)

- Google Search Console 속성 범위: https://support.google.com/webmasters/answer/34592?hl=ko
- Google 소유확인: https://support.google.com/webmasters/answer/9008080?hl=ko
- Google 사이트맵/정확한 lastmod/제출의 한계: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- Google JobPosting: https://developers.google.com/search/docs/appearance/structured-data/job-posting
- 네이버 표준 링크/검색 최적화: https://searchadvisor.naver.com/guide/seo-basic-intro
- 네이버 robots.txt: https://searchadvisor.naver.com/guide/seo-basic-robots
- 네이버 소유확인/비등록 사이트도 수집 가능: https://searchadvisor.naver.com/guide/faq-start-register
- 네이버 사이트 추가: https://help.naver.com/service/30010/contents/17584?lang=ko&osType=PC
