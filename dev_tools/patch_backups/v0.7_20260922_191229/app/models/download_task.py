from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DownloadTask:
    workshop_id: str
    title: str
    app_id: str
    mods_root: str
    auth_mode: str = "auto"
    username: str = ""
    status: str = "queued"
    message: str = ""
    attempts: int = 0
