from pathlib import Path
import xml.etree.ElementTree as ET

from .base import GameAdapter

class RimWorldAdapter(GameAdapter):
    APP_ID = "294100"

    def validate_mod_folder(self, mod_dir: Path) -> tuple[bool, str]:
        about_xml = mod_dir / "About" / "About.xml"
        if not about_xml.is_file():
            return False, "About/About.xml 이 없습니다."

        try:
            root = ET.parse(about_xml).getroot()
        except Exception as exc:
            return False, f"About.xml 파싱 실패: {exc}"

        name = (root.findtext("name") or "").strip()
        package_id = (root.findtext("packageId") or "").strip()
        return True, f"name={name or '?'} / packageId={package_id or '?'}"
