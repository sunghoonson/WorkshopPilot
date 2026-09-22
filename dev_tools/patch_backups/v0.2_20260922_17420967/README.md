# WorkshopPilot

Steam Workshop 모드를 탐색하고 SteamCMD로 내려받아 게임별 Mods 경로에 설치하는
Windows용 PySide6 GUI 프로젝트의 초기 골격입니다.

권장 설치 경로:

```text
C:\dev\WorkshopPilot
```

## 빠른 시작

1. ZIP을 `C:\dev\`에 압축 해제
2. `SETUP_VENV.bat`
3. `RUN.bat`

## 포함된 개발용 BAT

- `01_GITHUB_CONNECT.bat`
  - Git 저장소 초기화
  - `main` 브랜치 설정
  - GitHub `origin` 연결/교체
- `02_COMMIT_AND_PUSH.bat`
  - 변경 내용 확인
  - 커밋 메시지 입력
  - `git add -A`
  - commit + push
- `03_PROJECT_SNAPSHOT.bat`
  - 프로젝트 소스 ZIP
  - 프로젝트 트리 MD
  - 포함 파일 로그 생성

## 현재 구현 상태

- PySide6 메인 GUI 골격
- App ID / 게임명 입력
- SteamCMD 경로 선택
- Mods 경로 선택
- 설정 저장
- RimWorld(294100) 기본 프로필
- SteamCMD 명령 생성 계층
- 게임별 어댑터 구조
- RimWorld `About/About.xml` 검증 골격

Workshop 실제 검색/썸네일/다운로드 큐는 다음 단계에서 연결합니다.
