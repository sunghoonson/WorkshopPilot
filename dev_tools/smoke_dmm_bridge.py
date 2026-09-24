from __future__ import annotations
import json, sys, tempfile, zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.crimson_desert_archive import CrimsonDesertArchiveAnalyzer
from app.core.dmm_manager import DmmManager


def main() -> int:
    analyzer = CrimsonDesertArchiveAnalyzer()

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        archive = root / "Character Creator 837 8.0.3 2026-09-21T09-40Z.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Character Creator/mod.json", json.dumps({
                "modinfo": {
                    "title": "Character Creator",
                    "version": "8.0.3",
                    "author": "Khione",
                }
            }))
            zf.writestr("Character Creator/Character Creator.asi", b"MZ")
            for option in ("Human Female", "Human Male", "Orc Female", "Orc Male"):
                zf.writestr(
                    f"Character Creator/{option}/0009/character/test.xml",
                    b"<x/>",
                )

        result = analyzer.analyze(archive)
        assert result.requires_variant_choice
        assert result.recommended_manager == "dmm"
        assert result.format_id == "multi_variant_archive"
        assert "Human Female" in result.variant_options
        assert not result.can_install_with_cdumm

        dmm_zip = root / "dmm.zip"
        with zipfile.ZipFile(dmm_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("DMM.exe", b"MZ" + b"x" * (1024 * 1024 + 64))

        managed_root = root / "managed"

        class TestDmmManager(DmmManager):
            @property
            def managed_root(self) -> Path:
                return managed_root

        manager = TestDmmManager()
        exe = manager.import_local_package(dmm_zip)
        assert exe.is_file()
        assert manager.resolve() == ("managed", exe)

    print("[OK] DMM bridge / multi-variant smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
