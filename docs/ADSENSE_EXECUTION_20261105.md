# AdSense 신청 준비 추가 개선 · 2026-11-05

판정: **신청 보류**. 공개 접근 검사와 신청 준비, Google의 실제 승인은 별개다. 이번 변경은 PR 검토본이며 병합·공개 배포·심사 제출·광고 요청은 실행하지 않았다.

## 도메인 및 공식 기준

- AdSense 등록 주소: `https://kllollain-max.github.io` (공통 호스트 한 항목). `/careerpick/`, `/supportpick/`는 별도 사이트 등록 주소가 아니다. 두 프로젝트의 저장소·데이터·배포는 독립 유지한다.
- Google은 PSL 플랫폼 하위 도메인 등록을 허용한다. 공식 PSL에 github.io가 있다. 루트는 두 서비스 안내, 실제 계정 메타와 ads.txt가 공개되어 있다. 기존 계정의 소유확인 완료 표시는 과거 직접 확인 기록이며 이번에는 로그인 화면을 재검사하지 않았다.
- 독립 도메인은 선택 사항이다. 각각의 브랜드·심사를 분리할 수 있지만 구매·DNS·이전·canonical·기록 이전 비용과 검증이 따른다. 현재 공통 호스트로 먼저 준비할 수 있으므로 구매를 제안하거나 실행하지 않는다. 향후 독립 등록이 필요할 때 도메인 확정 후 승인한다.
- 루트 robots.txt·ads.txt는 `kllollain-max/kllollain-max.github.io`가 관리한다. 프로젝트 아래 ads.txt/robots.txt로 대체하지 않는다. 이번 두 PR에서 루트 저장소는 변경하지 않았다. 공유 호스트 파일은 두 서비스가 함께 영향을 받는다.
- 가치 있는 독자 콘텐츠·기만 방지·저작권·실제 처리에 맞는 개인정보 공개는 정책 준수 항목이다. 소개·문의·이용약관·사이트맵·Search Console 등록을 모두 일률적인 AdSense 필수 페이지라고 주장하지 않는다. 실제 광고 도입 전 지역·광고 설정에 맞는 동의/CMP와 개인정보 안내가 필요하다.
- 공식 근거: https://support.google.com/adsense/answer/12170421 · https://support.google.com/adsense/answer/2784438 · https://publicsuffix.org/list/public_suffix_list.dat · https://support.google.com/adsense/answer/7584263 · https://support.google.com/adsense/answer/7679060 · https://support.google.com/publisherpolicies/answer/11190248 · https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag

## 실제 추가 구현

`check_public_readiness.py`는 고정된 공개 호스트의 HTML/XML/TXT/JSON만 조회한다. 리디렉션을 따라가지 않고 JS·광고·SDK·외부 블로그를 실행하지 않는다. 루트의 게시자 메타와 ads.txt 일치, 사이트맵 범위·중복, 주요 정책·본문 페이지 canonical·noindex·H1, Google/광고 크롤러 robots 규칙을 검사한다. 공개 응답 해시를 영수증에 남긴다. 0=관찰 범위 통과, 1=오류, 2=미확인으로 실패를 숨기지 않는다. 읽기 전용 정기/배포 후 검사를 준비했으며 병합 전 운영 자동화로 간주하지 않는다.

검사에는 `none`(noindex,nofollow 동의어), Googlebot 전용 메타, 중복 메타와 HTTP 응답 차단 회귀를 추가했다. `max-image-preview:none`을 전체 색인 차단으로 오인하지 않는 사례도 검사한다. 이는 검사 누락 수정이며, 현재 운영 사이트의 색인 차단이 발견됐다는 뜻이 아니다.

## 보존·한계와 최종 적용

수집 원본·ID·사용자 기록 키·SNS 발행·웹푸시·R2 설정을 변경하지 않았다. 실제 수집·발송·구독·계약·결제·삭제를 실행하지 않았다. 기존 R2 PR #26은 실제 연결 증거가 별도로 필요하며 이번 점검으로 장기 백업 성공을 선언하지 않는다. main Git 이력과 보존 아티팩트는 유지된다. 신규 유료 자원 생성 없음.

이번에 실제 Android Chrome/휴대전화 설치·Core Web Vitals 현장 자료를 새로 측정하지 않았다. 기존 Chromium 크기별 검증은 과거 자료로만 재사용하고 실기기 검사로 확대하지 않는다. Search Console 제출·가져오기·발견·크롤링·색인 상태는 이번 HTTP 조회로 확정하지 않는다. 기존 홈 색인 관찰 기록이 전체 본문 색인을 뜻하지 않는다.

최종 순서: PR 후보 CI 확인 → 운영자 본문 검토·실제 개인정보 처리 확인 → 이 PR 두 개의 병합·공개 배포 승인 → 최신 main·최신 정상 자료로 배포 → 공개 변경·기능 재검증 → 공통 호스트 AdSense 검토 요청 승인·실행. 실제 광고 활성화는 동의/배치 구현 후 별도로 검증한다. 승인 가능성을 콘텐츠 개수나 검사 수로 보장하지 않는다.

되돌리기는 승인 PR의 공개/검사 변경만 역커밋한다. 전체 main을 과거로 되돌리거나 새 수집 자료·원장·개인 기록을 덮어쓰지 않는다.

## 커리어픽 결과

- 기존 PR #24를 재사용한다. 기존 구독 안내 정정·개인정보/사람 검토 자료는 유지한다. 별도 신규 PR로 같은 변경을 복제하지 않는다.
- 추가 파일: `scripts/check_public_readiness.py`, `tests/test_public_readiness.py`. 수정: `scripts/search_readiness.py`, `scripts/check_search_public.py`, `tests/test_public_search.py`, `.github/workflows/public-search-check.yml`, `.github/workflows/adsense-readiness-check.yml`, `guides/after-application-checklist.html`, 검토 reader/manifest.
- 콘텐츠: 신규 0편, 기존 1편 보강. 여러 공고의 접수·증빙·전형 구분표, 가상 기록 예시, 마감 시각 미확인·정정·접수상태 FAQ를 추가했다. 운영자 사람 검토는 0/6·대기 유지. 검토 후보 해시와 전체 본문도 갱신하여 공개본과 구분했다.
- 공개 URL 12/12 HTTP 200, canonical·본문·메타 정상, 사이트맵 XML 1,366 URL. 공개 현재 ALIO 723개에 사이트맵 누락 0, 중복 title/description 0, root robots 차단 0. 별도 호스트/대표 본문 12개 응답도 HTTP 200.
- 후보 로컬 재빌드 HTML 1,335 / 사이트맵 1,331 / 내부 링크 33,007 / 누락 0 / 원본 JSON 해시 보존. 이 수치는 PR #24 기준 보존 데이터이며 더 최신 공개 수집 723개와 같다고 주장하지 않는다. 후보는 데이터를 수정하지 않으므로 병합 시 최신 main 데이터가 유지되어야 한다. CI는 GitHub PR merge checkout을 검사한다.
- 로컬 Python 90개, Node 56개 통과. 새 회귀는 Python 8개. 공개 점검 2회 오류·미확인 0. 새 후보 CI는 PR의 실행 결과가 최종 근거다.
- 추가 일일 점검 예정: 08:35 KST. 기존 수집/발송 일정은 유지. 병합 전 미활성.
- 최신 main 관찰: `8f9eae5fa7194a45286a17c08ef860be26248704`. 최근 정기 배포 확인 실행 https://github.com/kllollain-max/careerpick/actions/runs/41987660431 은 Pages 배포·공개 해시 확인 성공. 실행 시작 SHA `c5799db943fb36a3dd8919c03fd491efaa7f5eb0`와 배포 결과 SHA는 구분해야 한다. 최근 수동 승인 배포는 https://github.com/kllollain-max/careerpick/actions/runs/41937987761 (`9e755e678cef70eb61ec42b8841bef80b07ba680`). 이번 PR의 신규 배포는 없다.
- 남음: 실제 사람 검토, 기관별 직무 본문 보강(보존 데이터의 직무분류가 실질 업무설명을 대신하지 않음), 운영 계약/개인정보 사실 확인, 실기기·성능 및 최신 Search Console 상태 확인. 웹푸시 실패는 별도 작업 범위로 남겨 두고 이번 PR에서 발송 장벽을 해제하지 않는다.
