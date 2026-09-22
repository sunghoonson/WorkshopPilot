# Changelog

## v0.2 - Workshop search foundation

- 실제 Steam 게임명 검색 추가
- 숫자 App ID 직접 조회 추가
- Steam Workshop 검색 페이지에서 Published File ID 수집
- `GetPublishedFileDetails` 공개 API로 제목/설명/태그/통계 보강
- 검색/게임 조회를 worker thread로 이동하여 GUI 블로킹 방지
- Workshop 썸네일 비동기 로딩
- 검색 결과 선택 시 상세 정보 표시
- Workshop 페이지 브라우저 열기
- `Mods\<Workshop ID>` 폴더 기준 설치 여부 표시
- 로그에 INFO/WARN/ERROR 및 시간 추가

다음 단계: SteamCMD QProcess 실행 + 다운로드 큐 + staging/검증/설치.
