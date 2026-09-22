# WorkshopPilot

Steam Workshop 모드를 검색하고 SteamCMD를 이용해 내려받은 뒤 게임별 Mods 폴더에 설치하는 Windows용 PySide6 GUI입니다.

권장 개발 경로:

```text
C:\dev\WorkshopPilot
```

## v0.3 핵심 동작

WorkshopPilot은 사용자가 SteamCMD를 별도로 설치하지 않아도 되도록 관리형 SteamCMD를 지원합니다.

```text
WorkshopPilot
  -> %LOCALAPPDATA%\WorkshopPilot\tools\steamcmd\steamcmd.exe
  -> steamapps\workshop\content\<AppID>\<WorkshopID>
  -> 게임 Mods 폴더\<WorkshopID>
```

관리형 SteamCMD가 없으면 `내장 설치/복구` 버튼으로 Valve 배포본을 자동 설치할 수 있습니다. 모드 다운로드를 눌렀을 때 SteamCMD가 전혀 없으면 자동 설치 여부를 묻습니다.

기존 외부 `steamcmd.exe`도 fallback으로 선택할 수 있습니다. 관리형과 외부 도구가 모두 있으면 관리형을 우선 사용합니다.


## v0.3.1 SteamCMD 초기화 보강

SteamCMD가 자체 업데이트 직후 Windows에서 종료 코드 `7`로 한 번 종료되며 재실행을 요구할 수 있습니다.
WorkshopPilot은 이 경우를 설치 실패로 확정하지 않고 자동으로 SteamCMD를 다시 실행합니다.

관리형 SteamCMD는 초기화가 실제로 끝난 뒤에만 준비 완료로 표시됩니다.


## Steam 인증

v0.4부터 세 가지 모드를 지원합니다.

```text
자동 (익명 우선)
익명
Steam 계정
```

`자동`은 먼저 익명 로그인을 사용하고, SteamCMD 출력이 인증/소유권 문제로 보일 때
Steam 계정 재시도를 제안합니다.

Steam 계정 모드에서도 **비밀번호와 Steam Guard 코드는 설정 파일에 저장하지 않습니다.**
SteamCMD가 입력을 요구할 때만 GUI에서 받아 실행 중인 프로세스의 표준 입력으로 전달합니다.

저장 가능한 값은 Steam 계정명뿐입니다.

## 빠른 시작

1. `SETUP_VENV.bat`
2. `RUN.bat`
3. `게임 / App ID`에 `294100` 입력 후 `게임 찾기`
4. Mods 경로 확인: `C:\games\RimWorld\Mods`
5. 필요하면 `내장 설치/복구`
6. Workshop에서 `Harmony` 검색
7. 항목 선택 후 `선택 모드 다운로드 / 설치`

RimWorld 다운로드 항목은 설치 전에 `About\About.xml`을 검사합니다. 기존 같은 Workshop ID 폴더가 있을 경우 새 파일을 임시 폴더에 검증한 뒤 교체하며, 교체 중 실패하면 기존 폴더를 복구하도록 구성했습니다.

## 개발 BAT

- `01_GITHUB_CONNECT.bat`: GitHub origin 연결
- `02_COMMIT_AND_PUSH.bat`: commit + push
- `03_PROJECT_SNAPSHOT.bat`: 프로젝트 ZIP / 트리 MD / 로그 생성

## 현재 제한

- 한 번에 한 개 모드 다운로드
- 익명 SteamCMD 로그인 사용
- SteamCMD 익명 다운로드가 허용되지 않는 Workshop 항목은 실패할 수 있음
- RimWorld 외 게임은 현재 범용 폴더 설치만 수행하며 게임별 검증기는 추후 추가
- 의존성 자동 설치 / Collection 가져오기 / 로드 순서 검증은 후속 단계
