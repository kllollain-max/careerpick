# 개인 기록 이전

구주소 https://jobinfo-hub.github.io/ 와 새주소 https://kllollain-max.github.io/careerpick/ 는 서로 다른 origin이므로 새사이트가 구주소 localStorage를 읽을 수 없다.

구주소를 사용하던 동일 기기·브라우저 프로필에서 나의 대시보드 → 데이터 백업(JSON)을 사용한다. 새사이트의 나의 대시보드 → 기록 복원에서 그 파일을 가져온다. 구주소 접근 불가 시 과거 내려받은 careerpick-backup JSON을 사용한다. 서버에는 개인 기록을 전송하지 않는다.

저장 키는 saved(공고 ID 배열), apps(ID별 상태·메모·일정·체크리스트), prefs, spec이다. ID a+ALIO공고번호를 유지한다. 가져오기 전 다운로드 백업과 기기 내 careerpick-before-import 복원 지점을 만든다. 저장 목록은 합집합, 같은 ID의 현재 상태·메모 우선, 가져온 충돌 원본은 careerpick-import-archive에 보관한다. 현재 공고와 연결되지 않는 ID도 삭제하지 않는다. 다시 가져와도 중복되지 않는다. 백업에는 충돌 보관함도 포함된다.

구주소의 실제 이용자 개인 기록 또는 개인 백업은 확보하지 않았다. **이전 기능 준비 완료 / 기존 기록 이전 미완료**. 실제 이전에는 구주소를 사용한 브라우저의 백업 파일이 필요하며 채팅·공개 저장소로 보낼 필요는 없다.
