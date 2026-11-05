# 기존 가이드 6편 내용 후속 검토

확인일: 2026-11-05(KST). 기준 main: `9f2dcd79e298787b74d2466ba0fe2a0daa9fb7bf`.

6편의 본문·가상 사례·실행 순서·체크리스트를 AI가 모두 읽었다. 이번 공식 재조회는 NCS FAQ·공정채용 자료의 공개 연결과 안내 범위 확인이다. 모든 채용기관의 현재 규칙이나 첨부 공고를 재검증한 결과가 아니다. 운영자의 사람 검토는 대기이며 포괄적인 계속 진행 요청을 검수 완료로 바꾸지 않는다.

## 수정

기존 본문을 유지하고 여섯 글에 동일하게 들어가 있던 '학습 시간·작성 틀' 안내를 글별 적용 범위로 바꿨다. STAR·학습계획·조건 해석·기록 방법을 NCS의 공식 평가 규칙으로 오해하지 않게 했다. 공개 안내를 '개정안'이라고만 부르던 문구를 현재 AI 점검 안내로 정리했다. 운영자의 검수 완료·작성자 자격·Google 승인을 추가하지 않았다.

| 문서 | 이번에 분명히 한 범위 | 후보 파일 SHA-256 | 사람 검토 |
|---|---|---|---|
| `application-checklist.html` | 이 글의 지원 준비표와 확인 순서는 커리어픽의 정리 방법입니다. 실제 모집단위·필수조건·증빙·마감시각은 지원할 공고와 정정 안내에서 확인하세요. | `695d15ae978051f49e849b75ce69057360294e77b59b99ec6da6ad8932408993` | 대기 |
| `qualification-preference-guide.html` | 이 글의 조건 분해 연습과 문의 문장은 커리어픽의 가상 예시입니다. 자격 인정 기준일·경력 산정·가점 적용은 개별 공고와 채용기관의 답변으로 확인해야 합니다. | `8412593ff419cf04bceae478a20da58c7399c5bee5de61284768a8ec9af20c46` | 대기 |
| `recruitment-corrections-guide.html` | 이 글의 변경 전·후·내 조치 기록법은 커리어픽의 제안입니다. 마감 연장이나 정정공고만으로 자격 기준일 변경·수정 허용·재접수 필요 여부를 확정하지 않습니다. | `481baf554e330413c87ed650b1b53bb1a2ab883dfdcf19bce9a2472d54b560b0` | 대기 |
| `self-introduction-star.html` | STAR 구성과 수정 예문은 경험을 정리하기 위한 커리어픽의 제안입니다. NCS나 모든 기관의 공식 평가 양식이 아니며, 실제 문항·블라인드 지침·본인의 사실을 우선합니다. | `f43f9466f45b82c2688fda293b1880715aaa24b6db056171f8224cb169a0fc2c` | 대기 |
| `ncs-study-plan.html` | 4주·2주 계획과 하루 90분은 커리어픽의 개인 학습 예시입니다. 한국산업인력공단의 권장 합격 일정이나 모든 기관의 출제 범위를 뜻하지 않습니다. 해당 공고의 시험 구성에 맞춰 조정하세요. | `ce2625524df2ec270de0830745a80c1ab5a26e0d73b6d534864fb36600fe1484` | 대기 |
| `after-application-checklist.html` | 접수 후 점검표와 커리어픽 기록·백업 순서는 준비를 돕는 자체 안내입니다. 커리어픽 메모나 출력물은 기관의 접수증을 대신하지 않으며, 실제 제출 상태와 변경 공지는 기관 시스템에서 확인하세요. | `2690ca08c8d16cd461f6d54530c2aadff103fd81808c4b06fd4761016f2a48c0` | 대기 |

## 개인정보와 계정

공개 개인정보처리방침의 미확인 계약·보유기간을 임의로 확정하지 않았다. `review-only/privacy-decision-20261105.md`에 운영자가 답할 최소 항목을 모았고 기존 5/30/90일 기준안과 계산기를 재사용한다. 자동 삭제·구독 변경·푸시 발송은 없다.

07:14 KST 계정 관찰에서 소유확인은 완료 표시, 사이트 심사는 미신청이었다. 오래된 확인표의 소유확인·지급정보 미완료 안내를 정정했다. 이 관찰 이후의 계정 상태를 실시간으로 보증하지 않는다.

## 공식 참고

- https://ncs.go.kr/th07/qna_faq.do?faqTypeCd=10&searchCondition=&searchKeyword=
- https://ncs.go.kr/blind/index.do

## 검증 범위

기존 정적 생성기·검색/게시자 검사를 재사용한다. 이번 변경에는 기록 저장 코드·공고 데이터·운영 워크플로 변경이 없다. 새 빌드 결과와 CI는 PR에 기록한다. 병합·배포·심사 제출·실제 광고 활성화는 실행하지 않는다.

## 배포 후 사람 검토본과 현재 대조 — 2026-11-05T09:24:51+09:00

기존 본문과 검토 기록을 재사용했다. [전체 본문 검토본](../review-only/content-review-reader-20261105.html)과 [버전·출처·미확인 사항 확인표](../review-only/content-review-manifest-20261105.json)를 함께 읽는다. 공개 빌드에는 포함하지 않는다. 사람 확인은 0건이며 계속 진행·배포 승인을 사람 검토로 기록하지 않았다.

| 제목·공개 URL | 본문 SHA-256 | 확인할 문장·미확인 사항 | 사람 검토 |
|---|---|---|---|
| [공공기관 채용 지원서 제출 후 확인할 8가지](https://kllollain-max.github.io/careerpick/guides/after-application-checklist.html) | `2690ca08c8d16cd461f6d54530c2aadff103fd81808c4b06fd4761016f2a48c0` | 최종 제출·접수번호·공식 공지 확인과 기록·백업 구분을 검토. 마감 후 문의가 접수 허용을 뜻하지 않음. | 대기 |
| [공공기관 채용공고, 지원 전에 확인할 7가지](https://kllollain-max.github.io/careerpick/guides/application-checklist.html) | `695d15ae978051f49e849b75ce69057360294e77b59b99ec6da6ad8932408993` | 필수 자격·기준일·실제 접수 시각·원문 정정 확인 순서를 검토. 접수번호와 개인 메모를 구분. | 대기 |
| [공기업 NCS 공부 순서와 4주 학습계획](https://kllollain-max.github.io/careerpick/guides/ncs-study-plan.html) | `ce2625524df2ec270de0830745a80c1ab5a26e0d73b6d534864fb36600fe1484` | 4주·2주·90분은 개인 계획 예시. 출제 범위·허용 준비물은 개별 공고가 우선임을 검토. | 대기 |
| [공공기관 채용공고의 지원자격·우대조건 읽는 법](https://kllollain-max.github.io/careerpick/guides/qualification-preference-guide.html) | `8412593ff419cf04bceae478a20da58c7399c5bee5de61284768a8ec9af20c46` | 필수·우대·가점·결격사유를 분리. 가상 조건을 실제 기관 규칙으로 일반화하지 않는지 검토. | 대기 |
| [공공기관 채용 정정공고가 나왔을 때 확인할 6가지](https://kllollain-max.github.io/careerpick/guides/recruitment-corrections-guide.html) | `481baf554e330413c87ed650b1b53bb1a2ab883dfdcf19bce9a2472d54b560b0` | 연장된 마감과 자격 기준일·수정·재제출 허용 여부를 별개로 다루는지 검토. | 대기 |
| [공기업 자기소개서 STAR 작성법과 수정 체크리스트](https://kllollain-max.github.io/careerpick/guides/self-introduction-star.html) | `f43f9466f45b82c2688fda293b1880715aaa24b6db056171f8224cb169a0fc2c` | STAR와 수정 예시는 자체 제안. 근거 없는 수치·합격 보장·기관 필수 양식으로 오해할 표현이 없는지 검토. | 대기 |

본문 버전은 위 소스 SHA와 해시에 고정한다. 이후 본문이 바뀌면 해당 범위의 재검토가 필요하다. 공개 가이드 6편은 HTTP 200이며 현재 원본 파일 해시와 일치한다. NCS 공식 자료를 다시 열었으나 모든 기관의 채용 규칙을 확인한 것은 아니다.

기존 절의 병합·공개 배포 미실행은 최초 작성 당시 상태다. PR #23는 승인 후 이미 병합·배포됐고, 이번 추가 후보는 별도 Draft PR 대상이다. 최신 검색·계정 결과는 [배포 후 점검](ADSENSE_SEARCH_FINALIZATION_20261105.md)을 따른다.
