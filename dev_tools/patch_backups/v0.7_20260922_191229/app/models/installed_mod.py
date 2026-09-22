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
