# WorkshopPilot Roadmap

## v0.1
- [x] PySide6 GUI skeleton
- [x] SteamCMD / Mods path settings
- [x] Game adapter structure
- [x] RimWorld adapter skeleton

## v0.2
- [x] Steam game/App ID search
- [x] Steam Workshop search
- [x] Workshop thumbnails/details
- [x] Installed mod detection

## v0.3
- [x] WorkshopPilot-managed SteamCMD install/repair
- [x] External SteamCMD fallback
- [x] QProcess SteamCMD execution
- [x] Live SteamCMD log
- [x] Workshop item download
- [x] Staging -> Mods install
- [x] RimWorld About.xml validation
- [x] Existing mod replacement rollback

## v0.4 candidates
- [ ] Download queue / multi-select
- [ ] Dependency detection and download
- [ ] Workshop Collection import
- [ ] Installed mod update comparison
- [ ] Multi-game profile editor
- [ ] Retry / failure metadata
- [ ] RimWorld load-order validation
- [ ] Search pagination / sort / tag UI

## v0.4 인증 단계 완료
- [x] 자동(익명 우선) 인증 모드
- [x] 익명 강제 모드
- [x] Steam 계정 모드
- [x] 익명 인증 실패 시 계정 fallback
- [x] 비밀번호/Steam Guard 비저장 처리
- [x] SteamCMD interactive credential stdin 처리

## v0.5 다운로드 큐 완료
- [x] 검색 결과 다중 체크
- [x] 단일/다중 다운로드를 공통 큐로 통합
- [x] 순차 SteamCMD 실행
- [x] 큐 상태 및 전체 진행률
- [x] 실패 항목 재시도
- [x] 큐 중지
- [x] 설치 성공 후 `[설치됨]` 즉시 갱신

## 다음 예정
- [ ] 설치된 모드 관리 탭
- [ ] Workshop 업데이트 시각과 로컬 설치 메타데이터 비교
- [ ] 설치된 모드 전체 업데이트
- [ ] RimWorld 의존성/로드 순서 진단

## v0.6 설치된 모드 관리 완료
- [x] 설치 모드 탭
- [x] Mods 폴더 스캔
- [x] RimWorld About.xml 메타데이터 표시
- [x] 로컬 검증 경고
- [x] 폴더 / Workshop 열기
- [x] 선택 재설치 / 업데이트
- [x] Workshop 모드 전체 업데이트
- [x] 다중 선택 삭제

## 다음 예정
- [ ] 설치 시 Workshop `time_updated` 로컬 메타데이터 저장
- [ ] 서버와 로컬 메타데이터 비교 후 `업데이트 있음` 표시
- [ ] 설치 모드 정렬 / 검색 / 필터
- [ ] RimWorld 의존성 및 loadAfter/loadBefore 진단

## v0.7 업데이트 추적 완료
- [x] 설치 시 Workshop time_updated 기준 저장
- [x] 설치 모드 원격 업데이트 일괄 확인
- [x] 최신 / 업데이트 있음 / 기준 없음 / 확인 불가 상태
- [x] 업데이트 있는 모드만 다운로드 큐 등록
- [x] 삭제 시 설치 메타데이터 정리

## 다음 예정
- [ ] 설치 모드 검색 / 정렬 / 상태 필터
- [ ] RimWorld dependencies / loadAfter / loadBefore 파싱
- [ ] 의존성 누락 자동 진단
- [ ] 권장 로드 순서 경고

## v0.8 RimWorld 진단 완료
- [x] modDependencies 파싱
- [x] loadAfter / loadBefore 파싱
- [x] incompatibleWith 파싱
- [x] ModsConfig 활성 순서 읽기
- [x] 누락 / 비활성 의존성 진단
- [x] 로드 순서 위반 진단
- [x] 비호환 / Package ID 중복 진단
- [x] 누락 의존성 Workshop 자동 다운로드 큐 등록

## 다음 예정
- [ ] 진단 결과 기반 안전한 권장 로드 순서 계산
- [ ] 적용 전 ModsConfig 자동 백업
- [ ] 사용자가 승인한 경우에만 로드 순서 쓰기
- [ ] 설치 모드 검색 / 상태 필터 / 정렬


## v0.10 Crimson Desert / Nexus
- [x] 로컬 Nexus ZIP 분석
- [x] crimson_browser_mod_v1 감지
- [x] 관리형 CDUMM
- [x] snapshot/import/apply 브리지
- [ ] Nexus API 인증/검색/다운로드
- [ ] nxm:// handler
- [ ] CDUMM 모드 목록/비활성/제거 UI
- [ ] Project Zomboid/Palworld Adapter
