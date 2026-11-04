# 지원금픽 사이트 검토본

커리어픽의 보존 백업 `161b601c`에서 검색·분야 칩·카드 CSS를 실제 추출해 재사용했다. 전체·맞춤·저장·지원 관리 흐름을 지원정보에 맞춰 다시 구현했다. 현재 main `ea7b62fc`와 비교했고 열린 PR #2, #11–15의 파일은 수정하지 않는다.

수정 담당: ChatGPT/Codex. 검토 담당: 미배정.

## 구현

- 전체 혜택, 키워드·분야·지역·지원방식 검색과 정렬
- 관심 지역·분야에 따른 맞춤 정보와 관련 이유
- 혜택 상세, 공식 안내 링크, 자료 조회·원문 수정 시각 구분
- 관심 저장, 직접 입력하는 신청 단계와 메모
- 지원금픽 전용 JSON 백업·가져오기, 기존 기록 우선 병합
- 다운로드가 제한된 환경을 위한 텍스트 백업·가져오기
- 별도 키 `supportpick:records:v1` 사용. 커리어픽의 `saved`, `prefs`, `apps`, `spec`은 읽거나 쓰지 않는다.
- 검색 조건·스크롤 보존과 상세 뒤로가기, 모바일 화면, 키보드 대화상자

## 실제 데이터 범위

보조금24 API 연결 시험에서 2026-11-04 13:05 KST에 확보한 **1건**을 사용한다. `data.json`과 `data.js`의 내용은 같아야 한다. 서비스ID, 공식 상세 URL, 구비서류 등을 원문에서 보존했다. 연결 성공을 신청 가능 판정으로 사용하지 않는다. 전체 목록 수집·정기 갱신은 아직 없다. `PROVENANCE.json`은 원본 백업·현재 참고 SHA와 응답 해시를 기록한다.

API 키, OneSignal, 광고·분석 스크립트, 서비스워커, SNS·네이버 코드를 복제하지 않는다. 별도 API 호출은 이번 사이트 제작에서 수행하지 않았다. 공개 전 본문·이용조건·재배포 조건·실제 접수 상태와 운영자 연락처를 확인해야 한다.

## 실행과 검증

`index.html`을 브라우저에서 열면 외부 의존성 없이 작동한다. 정적 HTTP 서버에서도 같은 경로로 동작한다. 기록 저장은 브라우저의 저장 공간 사용 허용 여부에 따른다.

```sh
node --test supportpick/tests/core.test.cjs
python3 supportpick/tools/build.py --output /tmp/supportpick-dist
```

`tools/build.py`는 허용된 공개 파일 9개만 복사하며 소스 문서·테스트·도구·백업 원본을 배포하지 않는다. `.nojekyll`은 출력에 생성한다. 원본 백업 ZIP은 공개 폴더에 포함하지 않는다.

## 같은 GitHub 계정에서 무료 운영

GitHub Free에서 공개 저장소의 Pages를 사용할 수 있다. 같은 `kllollain-max` 계정의 별도 공개 저장소 `supportpick`을 권장한다. 예상 주소는 `https://kllollain-max.github.io/supportpick/`이며 아직 만들거나 배포한 주소가 아니다.

별도 저장소에는 이 폴더를 저장소 루트로 복사한 뒤, 위 빌드 명령을 `python3 tools/build.py --output dist`로 실행한다. 배포 시 사이트 파일만 사용하고 테스트·문서·도구는 제외한다. 현재 앱은 상대 경로를 써 루트 또는 프로젝트 하위 경로에서 동작한다. 배포 주소를 확정한 다음 canonical·OG·사이트맵을 설정하고 미리보기의 noindex를 제거한다.

같은 `careerpick` 저장소의 `/supportpick/` 하위 경로도 가능하지만 별도 Pages 사이트가 아니라 한 배포의 일부다. 이 PR은 기존 `public-files.json`·배포 빌드·워크플로를 바꾸지 않아 커리어픽 운영 배포에 지원금픽을 자동 포함하지 않는다. 현재 저장소에서는 별도 검토 브랜치에 소스를 보존한다.

공식 문서: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages · https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits

## 승인 범위와 남은 단계

사용자의 2026-11-04 ‘커리어픽 사이트 백업, 저장본으로 지원금픽 사이트 만들어줘’ 요청에 따라 구현·격리 검증·Draft PR 준비를 수행한다. 기존 별도 승인 원칙에 따라 병합·공개 배포·예약 변경은 하지 않는다. 공개 전 별도 저장소 생성 또는 기존 저장소 하위 배포 중 최종 경로 확정, 데이터 수집 범위와 이용조건 확인, 운영자 안내 보완이 남는다.
