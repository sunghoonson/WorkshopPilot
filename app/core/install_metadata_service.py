from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


class InstallMetadataService:
    """
    Persist Workshop version baselines outside the game/mod directories.

    The stored `remote_time_updated` is the Steam Workshop timestamp observed
    when WorkshopPilot successfully installed/reinstalled that mod.
    """

    SCHEMA_VERSION = 1

    def __init__(self) -> None:
        self._lock = threading.RLock()

    @property
    def state_root(self) -> Path:
        if os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                return Path(local_app_data) / "WorkshopPilot" / "state"
            return Path.home() / "AppData" / "Local" / "WorkshopPilot" / "state"
        return Path.home() / ".local" / "share" / "WorkshopPilot" / "state"

    @property
    def database_path(self) -> Path:
        return self.state_root / "installations.json"

    def get(
        self,
        app_id: str,
        mods_root: Path,
        workshop_id: str,
    ) -> dict:
        key = self._make_key(app_id, mods_root, workshop_id)
        with self._lock:
            payload = self._load()
            value = payload.get("records", {}).get(key, {})
            return dict(value) if isinstance(value, dict) else {}

    def record_install(
        self,
        app_id: str,
        mods_root: Path,
        workshop_id: str,
        *,
        title: str = "",
        remote_time_updated: int = 0,
        destination: Path | None = None,
    ) -> None:
        app_id = str(app_id).strip()
        workshop_id = str(workshop_id).strip()
        if not app_id or not workshop_id:
            return

        mods_root = mods_root.resolve()
        key = self._make_key(app_id, mods_root, workshop_id)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            payload = self._load()
            records = payload.setdefault("records", {})
            records[key] = {
                "app_id": app_id,
                "mods_root": str(mods_root),
                "workshop_id": workshop_id,
                "title": str(title or ""),
                "remote_time_updated": self._to_int(remote_time_updated),
                "installed_at": now,
                "destination": str(
                    (destination or (mods_root / workshop_id)).resolve()
                ),
            }
            self._save(payload)

    def remove(
        self,
        app_id: str,
        mods_root: Path,
        workshop_id: str,
    ) -> None:
        key = self._make_key(app_id, mods_root, workshop_id)
        with self._lock:
            payload = self._load()
            records = payload.setdefault("records", {})
            if key in records:
                records.pop(key, None)
                self._save(payload)

    def _load(self) -> dict:
        path = self.database_path
        if not path.is_file():
            return {
                "schema_version": self.SCHEMA_VERSION,
                "records": {},
            }

        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {
                "schema_version": self.SCHEMA_VERSION,
                "records": {},
            }

        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("schema_version", self.SCHEMA_VERSION)
        payload.setdefault("records", {})
        return payload

    def _save(self, payload: dict) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        path = self.database_path
        temp = path.with_suffix(".json.tmp")

        with temp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        temp.replace(path)

    @staticmethod
    def _make_key(app_id: str, mods_root: Path, workshop_id: str) -> str:
        root = os.path.normcase(os.path.normpath(str(mods_root.resolve())))
        return f"{str(app_id).strip()}|{root}|{str(workshop_id).strip()}"

    @staticmethod
    def _to_int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
