from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.install_metadata_service import InstallMetadataService
from app.core.installed_mod_service import InstalledModService
from app.core.rimworld_diagnostic_service import RimWorldDiagnosticService


class TempMetadataService(InstallMetadataService):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root

    @property
    def state_root(self) -> Path:
        return self._root


HARMONY_XML = """<?xml version="1.0" encoding="utf-8"?>
<ModMetaData>
  <name>Harmony</name>
  <packageId>brrainz.harmony</packageId>
  <supportedVersions><li>1.6</li></supportedVersions>
  <loadBefore><li>ludeon.rimworld</li></loadBefore>
</ModMetaData>
"""

CHILD_XML = """<?xml version="1.0" encoding="utf-8"?>
<ModMetaData>
  <name>Child Mod</name>
  <packageId>example.child</packageId>
  <supportedVersions><li>1.6</li></supportedVersions>
  <modDependencies>
    <li>
      <packageId>brrainz.harmony</packageId>
      <displayName>Harmony</displayName>
      <steamWorkshopUrl>https://steamcommunity.com/sharedfiles/filedetails/?id=2009463077</steamWorkshopUrl>
    </li>
    <li>
      <packageId>example.missing</packageId>
      <displayName>Missing Lib</displayName>
      <steamWorkshopUrl>https://steamcommunity.com/sharedfiles/filedetails/?id=123456789</steamWorkshopUrl>
    </li>
  </modDependencies>
  <loadAfter><li>brrainz.harmony</li></loadAfter>
</ModMetaData>
"""


def write_mod(root: Path, folder: str, xml: str) -> None:
    about = root / folder / "About"
    about.mkdir(parents=True)
    (about / "About.xml").write_text(xml, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        mods = root / "Mods"
        mods.mkdir()

        write_mod(mods, "2009463077", HARMONY_XML)
        write_mod(mods, "999000111", CHILD_XML)

        config = root / "ModsConfig.xml"
        config.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<ModsConfigData>
  <activeMods>
    <li>ludeon.rimworld</li>
    <li>example.child</li>
    <li>brrainz.harmony</li>
  </activeMods>
</ModsConfigData>
""",
            encoding="utf-8",
        )

        metadata = TempMetadataService(root / "state")
        installed_service = InstalledModService(metadata=metadata)
        installed = installed_service.scan(mods, "294100")

        child = next(item for item in installed if item.package_id == "example.child")
        assert len(child.dependencies) == 2
        assert child.dependencies[1].workshop_id == "123456789"
        assert child.load_after == ("brrainz.harmony",)

        report = RimWorldDiagnosticService().analyze(
            installed,
            mods_config_path=config,
        )

        codes = [issue.code for issue in report.issues]
        assert "missing_dependency" in codes
        assert "load_after" in codes
        assert "load_before" in codes  # Harmony should be before Core, but isn't.

        missing = next(
            issue
            for issue in report.issues
            if issue.code == "missing_dependency"
        )
        assert missing.workshop_id == "123456789"

        assert len(report.active_mods) == 3
        assert report.error_count >= 1
        assert report.warning_count >= 1

    print("[OK] RimWorld dependency/load-order diagnostics smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
