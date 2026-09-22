from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.download_task import DownloadTask


def main() -> int:
    task = DownloadTask(
        workshop_id="2009463077",
        title="Harmony",
        app_id="294100",
        mods_root=r"C:\games\RimWorld\Mods",
        auth_mode="auto",
    )

    assert task.status == "queued"
    assert task.attempts == 0

    task.status = "downloading"
    task.attempts += 1
    assert task.status == "downloading"
    assert task.attempts == 1

    task.status = "completed"
    assert task.status == "completed"

    print("[OK] Download queue model smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
