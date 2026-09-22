from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from app.models.installed_mod import InstalledMod
from app.models.rimworld_diagnostic import (
    RimWorldActiveMod,
    RimWorldDiagnosticReport,
    RimWorldIssue,
)


class RimWorldDiagnosticService:
    """Analyze RimWorld dependencies and the active ModsConfig load order."""

    BUILTIN_NAMES = {
        "ludeon.rimworld": "Core",
        "ludeon.rimworld.royalty": "Royalty",
        "ludeon.rimworld.ideology": "Ideology",
        "ludeon.rimworld.biotech": "Biotech",
        "ludeon.rimworld.anomaly": "Anomaly",
        "ludeon.rimworld.odyssey": "Odyssey",
    }

    def default_mods_config_path(self) -> Path:
        if os.name == "nt":
            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                return (
                    Path(user_profile)
                    / "AppData"
                    / "LocalLow"
                    / "Ludeon Studios"
                    / "RimWorld by Ludeon Studios"
                    / "Config"
                    / "ModsConfig.xml"
                )

        return (
            Path.home()
            / "AppData"
            / "LocalLow"
            / "Ludeon Studios"
            / "RimWorld by Ludeon Studios"
            / "Config"
            / "ModsConfig.xml"
        )

    def analyze(
        self,
        installed_mods: list[InstalledMod],
        mods_config_path: Path | None = None,
    ) -> RimWorldDiagnosticReport:
        config_path = mods_config_path or self.default_mods_config_path()
        issues: list[RimWorldIssue] = []

        by_package: dict[str, InstalledMod] = {}
        duplicate_packages: dict[str, list[InstalledMod]] = {}

        for mod in installed_mods:
            package_id = self._norm(mod.package_id)
            if not package_id:
                continue

            if package_id in by_package:
                duplicate_packages.setdefault(
                    package_id,
                    [by_package[package_id]],
                ).append(mod)
            else:
                by_package[package_id] = mod

        for package_id, duplicates in duplicate_packages.items():
            names = ", ".join(mod.name for mod in duplicates)
            issues.append(
                RimWorldIssue(
                    severity="error",
                    code="duplicate_package_id",
                    mod_package_id=package_id,
                    mod_name=names,
                    related_package_id=package_id,
                    related_name=names,
                    message=(
                        f"동일한 Package ID '{package_id}'를 가진 모드가 "
                        f"{len(duplicates)}개 설치되어 있습니다: {names}"
                    ),
                )
            )

        active_ids: list[str] = []
        if not config_path.is_file():
            issues.append(
                RimWorldIssue(
                    severity="warning",
                    code="mods_config_missing",
                    mod_package_id="",
                    mod_name="RimWorld",
                    message=(
                        "ModsConfig.xml을 찾지 못했습니다. "
                        "설치된 의존성은 확인하지만 활성/로드 순서는 진단할 수 없습니다."
                    ),
                )
            )
        else:
            active_ids = self._parse_active_mods(config_path)

        active_index = {
            package_id: index
            for index, package_id in enumerate(active_ids)
        }

        active_rows: list[RimWorldActiveMod] = []
        for index, package_id in enumerate(active_ids):
            installed = by_package.get(package_id)
            built_in = self._is_builtin(package_id)

            if installed is not None:
                name = installed.name
                workshop_id = installed.workshop_id
                path = str(installed.path)
            else:
                name = self.BUILTIN_NAMES.get(package_id, package_id)
                workshop_id = ""
                path = ""

            active_rows.append(
                RimWorldActiveMod(
                    index=index,
                    package_id=package_id,
                    name=name,
                    installed=installed is not None,
                    built_in=built_in,
                    workshop_id=workshop_id,
                    path=path,
                )
            )

            if installed is None and not built_in:
                issues.append(
                    RimWorldIssue(
                        severity="warning",
                        code="active_missing_folder",
                        mod_package_id=package_id,
                        mod_name=name,
                        message=(
                            f"ModsConfig에는 활성화되어 있지만 현재 Mods 경로에서 "
                            f"Package ID '{package_id}'를 찾지 못했습니다."
                        ),
                    )
                )

        active_set = set(active_ids)
        installed_set = set(by_package)

        for mod in installed_mods:
            package_id = self._norm(mod.package_id)
            if not package_id:
                continue

            # Required dependencies.
            for dep in mod.dependencies:
                dep_id = self._norm(dep.package_id)
                if not dep_id:
                    continue

                related_name = (
                    dep.display_name
                    or self._display_name(dep_id, by_package)
                )

                present = dep_id in installed_set or self._is_builtin(dep_id)
                active = dep_id in active_set or self._is_builtin(dep_id)

                if not present:
                    issues.append(
                        RimWorldIssue(
                            severity="error",
                            code="missing_dependency",
                            mod_package_id=package_id,
                            mod_name=mod.name,
                            related_package_id=dep_id,
                            related_name=related_name,
                            workshop_id=dep.workshop_id,
                            message=(
                                f"{mod.name}이(가) 필수 모드 "
                                f"'{related_name or dep_id}'을(를) 요구하지만 "
                                f"현재 Mods 경로에서 찾지 못했습니다."
                            ),
                        )
                    )
                elif active_ids and not active:
                    issues.append(
                        RimWorldIssue(
                            severity="warning",
                            code="inactive_dependency",
                            mod_package_id=package_id,
                            mod_name=mod.name,
                            related_package_id=dep_id,
                            related_name=related_name,
                            workshop_id=dep.workshop_id,
                            message=(
                                f"{mod.name}의 필수 모드 "
                                f"'{related_name or dep_id}'은(는) 설치되어 있지만 "
                                "현재 RimWorld에서 활성화되어 있지 않습니다."
                            ),
                        )
                    )

            # Load-after rules.
            if package_id in active_index:
                mod_index = active_index[package_id]

                for target_raw in mod.load_after:
                    target = self._norm(target_raw)
                    if target not in active_index:
                        continue
                    if mod_index < active_index[target]:
                        issues.append(
                            RimWorldIssue(
                                severity="warning",
                                code="load_after",
                                mod_package_id=package_id,
                                mod_name=mod.name,
                                related_package_id=target,
                                related_name=self._display_name(target, by_package),
                                message=(
                                    f"{mod.name}은(는) "
                                    f"'{self._display_name(target, by_package)}' 뒤에 "
                                    "로드되어야 하지만 현재 더 앞에 있습니다."
                                ),
                            )
                        )

                for target_raw in mod.load_before:
                    target = self._norm(target_raw)
                    if target not in active_index:
                        continue
                    if mod_index > active_index[target]:
                        issues.append(
                            RimWorldIssue(
                                severity="warning",
                                code="load_before",
                                mod_package_id=package_id,
                                mod_name=mod.name,
                                related_package_id=target,
                                related_name=self._display_name(target, by_package),
                                message=(
                                    f"{mod.name}은(는) "
                                    f"'{self._display_name(target, by_package)}' 앞에 "
                                    "로드되어야 하지만 현재 더 뒤에 있습니다."
                                ),
                            )
                        )

            # Incompatibilities.
            for target_raw in mod.incompatible_with:
                target = self._norm(target_raw)
                if target not in installed_set and not self._is_builtin(target):
                    continue

                both_active = (
                    package_id in active_set
                    and (
                        target in active_set
                        or self._is_builtin(target)
                    )
                )
                issues.append(
                    RimWorldIssue(
                        severity="error" if both_active else "warning",
                        code="incompatible",
                        mod_package_id=package_id,
                        mod_name=mod.name,
                        related_package_id=target,
                        related_name=self._display_name(target, by_package),
                        message=(
                            f"{mod.name}이(가) "
                            f"'{self._display_name(target, by_package)}'와 "
                            + (
                                "동시에 활성화되어 있으며 비호환으로 선언되어 있습니다."
                                if both_active
                                else "비호환으로 선언된 모드가 설치되어 있습니다."
                            )
                        ),
                    )
                )

        severity_order = {"error": 0, "warning": 1, "info": 2}
        issues.sort(
            key=lambda issue: (
                severity_order.get(issue.severity, 9),
                issue.type_text,
                issue.mod_name.lower(),
                issue.related_name.lower(),
            )
        )

        return RimWorldDiagnosticReport(
            mods_config_path=config_path,
            active_mods=active_rows,
            issues=issues,
        )

    @staticmethod
    def _parse_active_mods(path: Path) -> list[str]:
        root = ET.parse(path).getroot()
        active = root.find("activeMods")
        if active is None:
            return []

        result: list[str] = []
        seen: set[str] = set()

        for child in list(active):
            value = (child.text or "").strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)

        return result

    def _display_name(
        self,
        package_id: str,
        by_package: dict[str, InstalledMod],
    ) -> str:
        mod = by_package.get(package_id)
        if mod is not None:
            return mod.name
        return self.BUILTIN_NAMES.get(package_id, package_id)

    @classmethod
    def _is_builtin(cls, package_id: str) -> bool:
        package_id = cls._norm(package_id)
        return package_id.startswith("ludeon.rimworld")

    @staticmethod
    def _norm(value: str) -> str:
        return str(value or "").strip().lower()
