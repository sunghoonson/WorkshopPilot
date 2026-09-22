# Architecture

- `app/core/workshop_service.py`: Workshop 검색
- `app/core/steamcmd_service.py`: SteamCMD 명령/실행
- `app/core/installer.py`: 스테이징 -> 최종 설치
- `app/games/`: 게임별 검증/메타데이터 처리
- `app/ui/`: PySide6 GUI

## 기본 원칙

1. GUI 메인 스레드는 블로킹하지 않는다.
2. SteamCMD 로그는 실시간으로 GUI에 전달한다.
3. 다운로드는 스테이징 후 검증한다.
4. 검증 성공 후에만 기존 모드를 교체한다.
5. 게임별 처리는 범용 Workshop 계층과 분리한다.
