# Changelog

## v0.4.1 - Korean SteamCMD bootstrap / exit-code 7 fix

- 한국어 SteamCMD의 `업데이트 완료! Steam 실행 중...` 메시지를 self-update restart로 인식
- 종료 코드 7을 단순 설치 실패로 처리하던 문제 수정
- 실제 Workshop 다운로드 도중 동일한 self-update가 발생해도 자동 재실행
- `steamcmd.exe`가 이미 내려받아진 경우 매번 ZIP을 재다운로드하지 않고 초기화부터 재개
- ready marker가 없지만 steamcmd.exe가 존재하면 GUI에 `초기화/복구 필요`로 표시
- 한국어/영어 bootstrap 로그를 검증하는 smoke test 추가

## v0.4 - Steam authentication modes

- `자동 (익명 우선) / 익명 / Steam 계정` 인증 방식 추가
- 자동 모드는 먼저 `login anonymous`로 시도
- Access Denied / No subscription / ownership/login 관련 오류를 감지하면 계정 재시도 제안
- Steam 계정 모드는 비밀번호를 명령줄 인자로 넘기지 않고 SteamCMD 프롬프트에 stdin으로 전달
- Steam Guard / 2단계 인증 프롬프트 처리
- 계정명은 설정에 저장 가능
- 비밀번호와 Steam Guard 코드는 파일에 저장하지 않음
- 기존 SteamCMD self-update 자동 재시도 유지

## v0.3.1 - SteamCMD self-update restart fix

- SteamCMD 최초 bootstrap 과정에서 `Update complete, launching...` 후 종료 코드 7이 발생하는 경우를 정상적인 self-update restart로 처리
- 관리형 SteamCMD 초기화 시 최대 4회 자동 재실행
- Workshop 다운로드 중 SteamCMD가 자체 업데이트되더라도 QProcess가 최대 3회 자동 재시도
- 관리형 SteamCMD가 실제 초기화에 성공한 경우에만 `.workshoppilot_ready` 마커를 생성
- 중간 초기화 실패 후 `steamcmd.exe`만 존재하는 상태를 `준비됨 (관리형)`으로 잘못 표시하지 않도록 수정

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
