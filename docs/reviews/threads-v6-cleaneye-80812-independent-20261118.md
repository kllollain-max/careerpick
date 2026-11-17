# 커리어픽 Threads v6.0 — cleaneye-80812 독립 검토와 v5 원고 (HOLD)

**공고 ID:** `cleaneye-80812` · **검토 대상:** 인천광역시부평구시설관리공단 2026년 제3회 직원 공개경쟁 채용시험 · **상태:** 미승인/비게시

## 공식 자료를 새로 대조한 항목

- 발행기관의 관할 자치단체 부평구청 공식 게시물(2026-10-30): https://www.icbp.go.kr/main/bbs/bbsMsgDetail.do?bcd=etcnotice&msg_seq=928
  - 공식 첨부 1: `★_[공고]_2026년_제3회_부평구시설관리공단_직원_공개경쟁_채용시험_공고.hwp` (117KB로 표시).
  - 공식 첨부 2: 응시원서 및 자기소개서 HWP (49KB), 첨부 3: 개인정보 동의서 HWPX (61KB).
  - 접수 기간은 **2026-11-09 09:00 ~ 2026-11-19 18:00 KST**, 방법은 **온라인**으로 게시됨. 해당 HTML을 이번 회차 실제 읽음.
- 고용24의 클린아이 연동 원문: https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?infoTypeCd=CLE&infoTypeGroup=tb_workinfocle&wantedAuthNo=20261030091023
  - 일반정규직, 전체 19명, 신입, 인천 지역제한(공고일 전일 인천 주민등록 주소), 자격/우대는 분야별 원문 참조.
  - 클린아이 canonical: https://job.cleaneye.go.kr/user/ypCareersData.do?idx=80812
- 공고문 전문을 열람했다는 제3자 채용 상세(원본의 독립적인 공식 수신증 *아님*): https://gongryak.com/postings/103181
  - 직렬별 11개 구분 및 **일반직 사무직 8급 3명**, 필기 NCS 25문항과 행정학·행정법 25문항, 인성검사 후 필기·면접 순서를 확인했음.
  - 나머지 정규직 직무별 인원과 공무직 제한경쟁은 섞지 않고 위 3명만 본문 소재로 선정함.
- 해당 제3자 페이지의 공식 Cleaneye HWP 링크도 실제 열기 시도했으나 HTTP 타임아웃으로 **원본 바이트/전문 직접 판독은 이 회차 미완료**. HWP 파일 SHA·문서 수정시각을 추정하거나 생성하지 않음.
- 공개된 공식 HTML에서는 변경/취소 공지 없음으로 보이지만 **변경·취소 전수 확인 아님**. 채용시스템의 개별 원서접수 URL 및 커리어픽 실제 직무 프로필 렌더링도 미검증.

## Threads v5 완성 문안 후보 (224 Unicode 코드포인트, 미승인)

```text
인천 공공기관 정규직 채용 소식!
부평구시설관리공단이 신입 직원을 모집해요.

전체 채용 19명 중 일반직 사무직 8급은 3명이에요.
사무직은 서류·인성검사·필기·면접 전형으로 진행하며, 필기는 NCS와 행정학·행정법 과목을 확인하세요.

원서 접수는 11월 19일 18시까지 온라인으로 진행돼요.
인천 거주 조건과 분야별 자격·우대사항은 공식 공고에서 꼭 확인하세요.

자세한 사항은 프로필링크 확인
```

정적 문구 검사: CTA 정확히 1회, URL·도메인·해시태그 없음, 단일 본문, 답글 0개, 문자 224개. 날짜는 2026년을 맥락상 표시하지 않았으나 운영 시 마감 전인지 재검증 필수. 이미지 제작·실제 카드 픽셀 검사 미완료.

## 승인 차단·후속 조건

**HOLD, 실게시 금지.** 공식 HWP 원본 전체와 실제 지원 양식·직무 자격조건을 독립적으로 다시 확보하여 직무별 요건·전형방식·마감시각을 정밀 확인해야 함. 공식 정정/취소, 원서접수 URL, 미게시 history, profile 상세, source raw SHA256, 해당 슬롯 24h 신선도, 이미지/텍스트 교대, `validate_entry` / `verify_official_receipt` / 카드 픽셀(필요시) / `threads_reviewed_ingest` / `queue_bridge` / remote CAS 전부 통과해야 실제 승인 공급 가능.

아직 `reviewed-submissions.json`, `reviewed-staging.json`, `writer-queue.json`, `threads_posted.json`, Meta POST를 변경하거나 진행하지 않았음. 기존 2026-11-18 정규 08·12·16·20 KST 승인 원고와 다른 저장소/기능은 보존.

## 2026-11-18 02:52 KST 공식 원본 수신 시험 결과 (미해결)

- [실제 실행 run 44141508892](https://github.com/kllollain-max/careerpick/actions/runs/44141508892), commit `cac4b27377a6c32368774366848e4de38b49c221`, **completed/failure**.
- Cleaneye 정확한 공식 HWP 첨부 `job.cleaneye.go.kr/file/FileDownload.do` 에 3회 유한 시도 (2초·4초 백오프); 매회 HTTPS 연결 제한시간 10초 초과, 마지막 `requests.exceptions.ConnectTimeout` 로 종료.
- 증거 artifact [14353219848](https://github.com/kllollain-max/careerpick/actions/runs/44141508892/artifacts/14353219848)에 `downloaded=false, parsed=false, verified_meaning=false, approved=false, cas_updated=false, meta_posted=false` 보존됨. **SHA-256 및 공식 전문 미확보**. 근거를 취득한 것처럼 검토시간을 갱신하거나 기존 보류를 해제하지 않음.
- 별도 부평구청 공식 HTML 공고는 다시 읽을 수 있으나 HWP 원문 수신증을 대신하지 못함. 공식 HWP 원본 다운로드가 가능한 기관 대체 주소가 발견되면 정확 도메인/경로만 고정하여 재시도하고, 그 전에는 HOLD 유지. 위 단일 브랜치 외 운영 코드는 미변경.
