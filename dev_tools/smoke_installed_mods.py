from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.installed_mod_service import InstalledModService


ABOUT_XML = """<?xml version="1.0" encoding="utf-8"?>
<ModMetaData>
  <name>Smoke Test Mod</name>
  <author>WorkshopPilot</author>
  <packageId>workshoppilot.smoke</packageId>
  <supportedVersions>
    <li>1.5</li>
    <li>1.6</li>
  </supportedVersions>
</ModMetaData>
"""


def main() -> int:
    service = InstalledModService()

    with tempfile.TemporaryDirectory() as temp:
        mods = Path(temp) / "Mods"
        mod = mods / "1234567890"
        about = mod / "About"
        about.mkdir(parents=True)
        (about / "About.xml").write_text(ABOUT_XML, encoding="utf-8")

        items = service.scan(mods, "294100")
        assert len(items) == 1
        item = items[0]

        assert item.name == "Smoke Test Mod"
        assert item.workshop_id == "1234567890"
        assert item.package_id == "workshoppilot.smoke"
        assert item.supported_versions == ("1.5", "1.6")
        assert item.valid

        service.delete(mods, mod)
        assert not mod.exists()

    print("[OK] Installed mod scan/delete smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
