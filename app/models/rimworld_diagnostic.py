from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True, frozen=True)
class RimWorldDependency:
    package_id: str
    display_name: str = ""
    steam_workshop_url: str = ""
    download_url: str = ""
    workshop_id: str = ""


@dataclass(slots=True)
class RimWorldActiveMod:
    index: int
    package_id: str
    name: str = ""
    installed: bool = False
    built_in: bool = False
    workshop_id: str = ""
    path: str = ""

    @property
    def status_text(self) -> str:
        if self.built_in:
            return "바닐라/DLC"
        if self.installed:
            return "설치됨"
        return "파일 없음"


@dataclass(slots=True)
class RimWorldIssue:
    severity: str
    code: str
    mod_package_id: str
    mod_name: str
    related_package_id: str = ""
    related_name: str = ""
    workshop_id: str = ""
    message: str = ""

    @property
    def severity_text(self) -> str:
        return {
            "error": "오류",
            "warning": "경고",
            "info": "정보",
        }.get(self.severity, self.severity)

    @property
    def type_text(self) -> str:
        return {
            "missing_dependency": "필수 모드 누락",
            "inactive_dependency": "필수 모드 비활성",
            "load_after": "로드 순서",
            "load_before": "로드 순서",
            "incompatible": "비호환",
            "duplicate_package_id": "Package ID 중복",
            "active_missing_folder": "활성 모드 파일 없음",
            "mods_config_missing": "ModsConfig 없음",
        }.get(self.code, self.code)


@dataclass(slots=True)
class RimWorldDiagnosticReport:
    mods_config_path: Path
    active_mods: list[RimWorldActiveMod] = field(default_factory=list)
    issues: list[RimWorldIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def info_count(self) -> int:
        return sum(issue.severity == "info" for issue in self.issues)
