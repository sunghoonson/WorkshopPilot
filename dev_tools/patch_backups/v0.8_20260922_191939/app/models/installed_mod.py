from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class InstalledMod:
    folder_name: str
    path: Path
    name: str
    workshop_id: str = ""
    package_id: str = ""
    author: str = ""
    supported_versions: tuple[str, ...] = ()
    valid: bool = True
    message: str = ""
    installed_remote_time_updated: int = 0
    remote_time_updated: int = 0
    update_status: str = "unknown"

    @property
    def workshop_url(self) -> str:
        if not self.workshop_id:
            return ""
        return (
            "https://steamcommunity.com/sharedfiles/filedetails/"
            f"?id={self.workshop_id}"
        )

    @property
    def versions_text(self) -> str:
        return ", ".join(self.supported_versions) if self.supported_versions else "-"


    @property
    def update_status_text(self) -> str:
        return {
            "latest": "최신",
            "update_available": "업데이트 있음",
            "baseline_missing": "기준 없음",
            "check_required": "확인 필요",
            "unavailable": "확인 불가",
            "local": "로컬",
        }.get(self.update_status, self.update_status or "-")

    @property
    def needs_update(self) -> bool:
        return self.update_status == "update_available"
