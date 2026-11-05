# 배포 후 AdSense·검색 최종화 점검

2026-11-05 KST · 판정: 운영자 확인 대기. 신규 후보의 병합·공개 배포·심사 신청·광고 활성화 미실행.

소스 검토 기준 `9e755e678cef70eb61ec42b8841bef80b07ba680`. 기존 PR #23와 이후 상호 배너·블로그 변경을 보존한다. 최신 main이 움직이면 승인 배포 전 다시 비교한다.

## 실제 검색 상태

해당 URL 접두어 속성은 공식 설정 화면에서 인증된 소유자로 표시됐다. 사이트맵은 가져올 수 없음·마지막 읽기 11/4·발견 0이다. 새 공개 검사에서는 HTTP 200·유효 XML·정규 경로로 정상이다. Google 재처리 지연 가능성을 확정 원인으로 단정하지 않고 수집 실패의 실제 내부 원인은 미확인으로 남긴다. 중복 제출·무차별 색인 요청은 하지 않았다.

| URL | 실제 Google 색인 | Google 선택 canonical | 확인 시각 |
|---|---|---|---|
| https://kllollain-max.github.io/careerpick/ | 색인 생성됨 | https://kllollain-max.github.io/careerpick/ | 2026-11-05 09:13 KST |
| https://kllollain-max.github.io/careerpick/guides/application-checklist.html | 크롤링됨 — 현재 색인이 생성되지 않음 | https://kllollain-max.github.io/careerpick/guides/application-checklist.html | 2026-11-05 09:14 KST |
| https://kllollain-max.github.io/careerpick/guides/self-introduction-star.html | Google에 아직 알려지지 않음 | 해당사항 없음 | 2026-11-05 09:15 KST |
| https://kllollain-max.github.io/careerpick/jobs/a306665.html | 크롤링됨 — 현재 색인이 생성되지 않음 | https://kllollain-max.github.io/careerpick/jobs/a306665.html | 2026-11-05 09:16 KST |
| https://kllollain-max.github.io/careerpick/jobs/a306677.html | Google에 아직 알려지지 않음 | 해당사항 없음 | 2026-11-05 09:17 KST |

Google 실시간 테스트 결과와 실제 색인은 다르다. STAR 가이드 09:15:08 테스트는 가져오기 성공·수집/색인 허용이지만 실제 색인은 미생성이다. 다른 사이트 표본의 실시간 결과는 별도 관찰 기록을 따른다. 과거 공개 HTML 전수 검사를 실제 색인 증거로 사용하지 않는다.

## AdSense 공통 호스트

`kllollain-max.github.io` 한 개의 등록 단위로 표시된다. 소유확인 단계 녹색 완료, 지급 홈 카드 정보 확인, 사이트 검토 필요·검토 요청 버튼을 확인했다. ads.txt 계정은 찾을 수 없음(11/4 17:21 KST 업데이트), 공개 루트는 새 검사에서 HTTP 200·실제 계정 게시자 행 일치, 메타도 일치했다. 올바른 파일을 다시 쓰거나 하위 중복 파일을 추가하지 않았다. 실제 검토 요청·광고 스크립트 삽입·자동광고 활성화·계약 동의 없음. 계정 세부 정보·식별자를 공개 보고에 넣지 않는다.

## 콘텐츠·개인정보·광고 경계

[본문별 버전 확인표](CONTENT_REVIEW_20261105.md)와 [전체 원고](../review-only/content-review-reader-20261105.html)를 함께 읽는다. 사람 검토 완료 0/6이며 실제 검토자 확인이 필요하다. 기존 5/30/90일은 제안이다. [운영자 결정·처리 대조표](../review-only/privacy-decision-20261105.md)에 남은 담당·기간·사본·외부 계약 확인을 모았다.

Google 광고는 독자적 가치가 없는 복제/자동 수집 화면에 배치하지 않는다. 검토된 가이드·해설을 먼저 후보로 보되 사람 검토와 실질적 선별·편집을 확인한다. 개인 관리·빈 결과·오류·로딩·미완성 화면은 초기 제외한다. 실제 광고 전 데이터 이용·쿠키·제3자·선택권, 방문 지역별 동의 및 인증 CMP 적용을 확인한다. 사이트맵·색인 개수를 AdSense의 고정 신청 필수조건으로 만들지 않는다.

## 이번 후보 검증과 배포

새 로컬 검사와 재빌드는 수행했으며 원격 CI·320/390/1440px 검토 결과와 최종 후보 SHA는 PR에 기록한다. 검토 자료는 공개 빌드 밖에 둔다. 구독 완료 문구만 실제 발송 성공과 구분했고 동작·설정을 변경하지 않았다.

되돌리기는 이번 문구·검토 자료만 역커밋한다. 원본 데이터·개인 기록·기존 배너/블로그·수집·외부 자동화를 초기화하지 않는다. 새 병합·공개 배포, 사람 검토, 개인정보 결정, 심사 제출, 광고 활성화는 각각 구분해 승인받는다.

공식 근거:
- https://support.google.com/adsense/answer/9724
- https://support.google.com/publisherpolicies/answer/11190248
- https://support.google.com/adsense/answer/7584263?hl=ko
- https://support.google.com/adsense/answer/7679060
- https://support.google.com/adsense/answer/1348695
- https://support.google.com/adsense/answer/13554116
- https://developers.google.com/search/docs/essentials/technical
- https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl

## 새 화면 검증 완료

2026-11-05: 전체 26건 검토 문서·지원금픽 개인정보 후보·커리어픽 구독 완료 문구를 320/390/1440px HTTP 프레임 9개에서 확인했다. 가로 넘침 0, 검토 본문 26개 표시. 실제 휴대폰·설치·구독·발송 시험과 구분한다. 구독 문구는 후보에서 추출한 읽기 전용 배치 검토다.

지원금픽 교통비 해설은 09:20:34 KST Google 실시간 테스트에서 가져오기 성공·수집 및 색인 허용으로 나왔으나, 실제 Google 색인 탭은 아직 알려지지 않은 URL이다. 새 심사·광고·삭제·운영 설정 변경은 실행하지 않았다.
