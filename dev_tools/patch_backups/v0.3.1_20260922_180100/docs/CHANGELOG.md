# Changelog

## v0.3 - Managed SteamCMD + Workshop install

- WorkshopPilot 관리형 SteamCMD 런타임 추가
  - `%LOCALAPPDATA%\WorkshopPilot\tools\steamcmd`
  - Valve 배포 ZIP 자동 다운로드
  - 안전한 ZIP 경로 검사 후 압축 해제
  - 최초 실행/자체 업데이트 초기화
- 기존 외부 SteamCMD 경로 fallback 유지
- GUI의 직접 SteamCMD 경로 입력을 `Steam 도구` 상태 표시로 변경
- `내장 설치/복구`, `외부 도구 선택` 버튼 추가
- SteamCMD 실행을 `QProcess`로 연결하여 GUI 메인 스레드 블로킹 방지
- SteamCMD 실시간 출력을 GUI 로그에 표시
- 선택한 Workshop 항목 실제 다운로드 기능 연결
- 다운로드 완료 후 지정된 Mods 폴더로 자동 설치
- RimWorld는 `About/About.xml` 검증 후 설치
- 기존 모드 갱신 시 임시 복사 + 기존 폴더 백업 + 실패 시 롤백
- 등록되지 않은 게임으로 전환하면 이전 게임의 Mods 경로를 그대로 사용하지 않도록 보호

## v0.2 - Workshop search

- 게임명 / App ID 검색
- Steam Workshop 검색
- 썸네일 및 상세 정보 표시
- 설치 여부 표시
- Workshop 페이지 열기
