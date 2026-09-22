from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Callable


Validator = Callable[[Path], tuple[bool, str]]


def install_mod_folder(
    source: Path,
    mods_root: Path,
    destination_name: str,
    validator: Validator | None = None,
) -> Path:
    """Copy a downloaded mod into the target Mods directory with validation and rollback."""
    source = source.resolve()
    mods_root = mods_root.resolve()

    if not source.is_dir():
        raise FileNotFoundError(f"다운로드 원본 폴더가 없습니다: {source}")
    if not any(source.iterdir()):
        raise RuntimeError(f"다운로드 원본 폴더가 비어 있습니다: {source}")

    if validator is not None:
        ok, detail = validator(source)
        if not ok:
            raise RuntimeError(f"모드 검증 실패: {detail}")

    mods_root.mkdir(parents=True, exist_ok=True)
    destination = mods_root / destination_name
    token = uuid.uuid4().hex[:8]
    temp = mods_root / f".workshoppilot_tmp_{destination_name}_{token}"
    backup = mods_root / f".workshoppilot_backup_{destination_name}_{token}"

    try:
        shutil.copytree(source, temp)

        if validator is not None:
            ok, detail = validator(temp)
            if not ok:
                raise RuntimeError(f"복사 후 모드 검증 실패: {detail}")

        if destination.exists():
            destination.rename(backup)

        temp.rename(destination)

        if backup.exists():
            shutil.rmtree(backup)

        return destination
    except Exception:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
        if backup.exists() and not destination.exists():
            backup.rename(destination)
        raise
