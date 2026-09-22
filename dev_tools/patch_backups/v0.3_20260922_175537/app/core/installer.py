from __future__ import annotations

import shutil
from pathlib import Path

def install_mod_folder(
    source: Path,
    mods_root: Path,
    destination_name: str,
) -> Path:
    """스테이징된 모드 폴더를 최종 Mods 경로로 복사하는 초기 구현."""
    source = source.resolve()
    mods_root = mods_root.resolve()
    destination = mods_root / destination_name

    mods_root.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        shutil.rmtree(destination)

    shutil.copytree(source, destination)
    return destination
