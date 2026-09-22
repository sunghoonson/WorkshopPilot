from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from app.core.install_metadata_service import InstallMetadataService
from app.models.installed_mod import InstalledMod


class InstalledModService:
    """Scan and safely manage mods already present in a game\'s Mods directory."""

    def __init__(self, metadata: InstallMetadataService | None = None) -> None:
        self.metadata = metadata or InstallMetadataService()

    _INTERNAL_PREFIXES = (
        ".workshoppilot_tmp_",
        ".workshoppilot_backup_",
    )

    def scan(self, mods_root: Path, app_id: str) -> list[InstalledMod]:
        mods_root = mods_root.expanduser()
        if not mods_root.exists():
            return []
        if not mods_root.is_dir():
            raise NotADirectoryError(f"Mods 경로가 폴더가 아닙니다: {mods_root}")

        result: list[InstalledMod] = []
        for child in sorted(
            (p for p in mods_root.iterdir() if p.is_dir()),
            key=lambda p: p.name.lower(),
        ):
            if child.name.startswith(self._INTERNAL_PREFIXES):
                continue

            if str(app_id) == "294100":
                item = self._scan_rimworld(child, mods_root, str(app_id))
            else:
                item = self._scan_generic(child, mods_root, str(app_id))
            result.append(item)

        result.sort(
            key=lambda item: (
                not bool(item.workshop_id),
                item.name.lower(),
                item.folder_name.lower(),
            )
        )
        return result

    def delete(self, mods_root: Path, mod_path: Path) -> None:
        mods_root = mods_root.resolve()
        mod_path = mod_path.resolve()

        if mod_path == mods_root:
            raise RuntimeError("Mods 루트 폴더 자체는 삭제할 수 없습니다.")
        if mod_path.parent != mods_root:
            raise RuntimeError(
                "안전 검증 실패: 선택한 모드가 현재 Mods 경로의 직접 하위 폴더가 아닙니다."
            )
        if not mod_path.exists():
            return
        if not mod_path.is_dir():
            raise RuntimeError(f"삭제 대상이 폴더가 아닙니다: {mod_path}")

        shutil.rmtree(mod_path)

    def _scan_generic(
        self,
        mod_dir: Path,
        mods_root: Path,
        app_id: str,
    ) -> InstalledMod:
        workshop_id = mod_dir.name if mod_dir.name.isdigit() else ""
        record = self.metadata.get(app_id, mods_root, workshop_id) if workshop_id else {}
        baseline = self._to_int(record.get("remote_time_updated"))
        return InstalledMod(
            folder_name=mod_dir.name,
            path=mod_dir,
            name=mod_dir.name,
            workshop_id=workshop_id,
            installed_remote_time_updated=baseline,
            update_status=("check_required" if baseline else "baseline_missing")
            if workshop_id else "local",
        )

    def _scan_rimworld(
        self,
        mod_dir: Path,
        mods_root: Path,
        app_id: str,
    ) -> InstalledMod:
        workshop_id = mod_dir.name if mod_dir.name.isdigit() else ""
        record = self.metadata.get(app_id, mods_root, workshop_id) if workshop_id else {}
        baseline = self._to_int(record.get("remote_time_updated"))
        update_status = (
            "check_required" if workshop_id and baseline
            else "baseline_missing" if workshop_id
            else "local"
        )
        about_xml = mod_dir / "About" / "About.xml"

        if not about_xml.is_file():
            return InstalledMod(
                folder_name=mod_dir.name,
                path=mod_dir,
                name=mod_dir.name,
                workshop_id=workshop_id,
                valid=False,
                message="About/About.xml 없음",
                installed_remote_time_updated=baseline,
                update_status=update_status,
            )

        try:
            root = ET.parse(about_xml).getroot()
        except Exception as exc:
            return InstalledMod(
                folder_name=mod_dir.name,
                path=mod_dir,
                name=mod_dir.name,
                workshop_id=workshop_id,
                valid=False,
                message=f"About.xml 파싱 실패: {exc}",
                installed_remote_time_updated=baseline,
                update_status=update_status,
            )

        name = (root.findtext("name") or mod_dir.name).strip()
        package_id = (root.findtext("packageId") or "").strip()
        author = (
            (root.findtext("author") or "").strip()
            or (root.findtext("authors") or "").strip()
        )

        versions: list[str] = []
        supported = root.find("supportedVersions")
        if supported is not None:
            for child in list(supported):
                value = (child.text or "").strip()
                if value and value not in versions:
                    versions.append(value)

        # Older mods may expose one target version instead.
        target_version = (root.findtext("targetVersion") or "").strip()
        if target_version and target_version not in versions:
            versions.append(target_version)

        return InstalledMod(
            folder_name=mod_dir.name,
            path=mod_dir,
            name=name,
            workshop_id=workshop_id,
            package_id=package_id,
            author=author,
            supported_versions=tuple(versions),
            valid=True,
            message="정상",
            installed_remote_time_updated=baseline,
            update_status=update_status,
        )


    @staticmethod
    def _to_int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
