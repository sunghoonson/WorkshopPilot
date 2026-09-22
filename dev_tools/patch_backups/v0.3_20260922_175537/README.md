# WorkshopPilot

Steam Workshop 모드를 탐색하고 SteamCMD로 내려받아 게임별 Mods 경로에 설치하는
Windows용 PySide6 GUI 프로젝트입니다.

권장 설치 경로:

```text
C:\dev\WorkshopPilot
```

## v0.2 현재 기능

- 게임 이름 검색 → Steam App ID 선택
- 숫자 App ID 직접 조회
- App ID 기준 Steam Workshop 키워드 검색
- Workshop 제목 / ID / 상세 설명 / 태그 / 통계 표시
- Workshop 미리보기 이미지 로딩
- 지정 Mods 경로에서 `Workshop ID` 폴더 설치 여부 감지
- Workshop 페이지 브라우저 열기
- GUI 네트워크 작업을 worker thread로 실행하여 메인 UI 블로킹 방지

아직 SteamCMD 실제 다운로드 버튼은 연결하지 않았습니다. 다음 단계에서
`QProcess -> SteamCMD -> staging -> Mods 경로 검증/설치` 순서로 구현합니다.

## 빠른 시작

1. `SETUP_VENV.bat`
2. `RUN.bat`
3. `294100` 입력 후 `게임 찾기`
4. Workshop 검색에 `Harmony` 입력 후 검색

RimWorld 기본 Mods 경로는 다음과 같습니다.

```text
C:\games\RimWorld\Mods
```

## 개발용 BAT

- `01_GITHUB_CONNECT.bat`: Git 초기화 / origin 연결
- `02_COMMIT_AND_PUSH.bat`: add / commit / push
- `03_PROJECT_SNAPSHOT.bat`: 소스 ZIP + 트리 MD + 로그 생성
