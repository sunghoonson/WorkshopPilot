from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.install_metadata_service import InstallMetadataService
from app.models.installed_mod import InstalledMod


class TempMetadataService(InstallMetadataService):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root

    @property
    def state_root(self) -> Path:
        return self._root


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        service = TempMetadataService(root / "state")
        mods = root / "Mods"
        mods.mkdir()

        service.record_install(
            "294100",
            mods,
            "2009463077",
            title="Harmony",
            remote_time_updated=100,
            destination=mods / "2009463077",
        )

        record = service.get("294100", mods, "2009463077")
        assert record["remote_time_updated"] == 100
        assert record["title"] == "Harmony"

        mod = InstalledMod(
            folder_name="2009463077",
            path=mods / "2009463077",
            name="Harmony",
            workshop_id="2009463077",
            installed_remote_time_updated=100,
            remote_time_updated=200,
            update_status="update_available",
        )
        assert mod.needs_update
        assert mod.update_status_text == "업데이트 있음"

        service.remove("294100", mods, "2009463077")
        assert service.get("294100", mods, "2009463077") == {}

        payload = json.loads(service.database_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1

    print("[OK] Workshop update tracking smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
