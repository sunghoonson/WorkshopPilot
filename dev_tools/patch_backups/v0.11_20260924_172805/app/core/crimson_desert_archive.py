from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class CrimsonArchiveAnalysis:
    archive_path: Path
    valid_archive: bool
    format_id: str = "unknown"
    title: str = ""
    author: str = ""
    version: str = ""
    description: str = ""
    nexus_mod_id: str = ""
    root_prefix: str = ""
    file_count: int = 0
    total_uncompressed_bytes: int = 0
    extensions: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    manifest: dict = field(default_factory=dict)

    @property
    def can_install_with_cdumm(self) -> bool:
        return self.valid_archive and self.format_id in {
            "crimson_browser_mod_v1",
            "cdumm_supported_archive",
        }

    @property
    def size_text(self) -> str:
        value = float(self.total_uncompressed_bytes)
        units = ("B", "KB", "MB", "GB")
        idx = 0
        while value >= 1024.0 and idx < len(units) - 1:
            value /= 1024.0
            idx += 1
        return f"{value:.1f} {units[idx]}"

    def to_display_text(self) -> str:
        lines = [
            f"파일: {self.archive_path}",
            f"형식: {self.format_id}",
            f"제목: {self.title or '-'}",
            f"저작자: {self.author or '-'}",
            f"버전: {self.version or '-'}",
            f"Nexus Mod ID: {self.nexus_mod_id or '-'}",
            f"파일 수: {self.file_count}",
            f"압축 해제 기준 크기: {self.size_text}",
            f"루트 폴더: {self.root_prefix or '(없음)'}",
            f"확장자: {', '.join(self.extensions) or '-'}",
        ]
        if self.description:
            lines += ["", "설명:", self.description]
        if self.risk_flags:
            lines += ["", "주의:", *[f"- {x}" for x in self.risk_flags]]
        if self.notes:
            lines += ["", "판정:", *[f"- {x}" for x in self.notes]]
        return "\n".join(lines)


class CrimsonDesertArchiveAnalyzer:
    SCRIPT_EXTENSIONS = {
        ".exe", ".dll", ".asi", ".bat", ".cmd", ".ps1", ".py", ".com",
    }
    CDUMM_DIRECT_EXTENSIONS = {
        ".7z", ".rar", ".json", ".cdmod", ".asi", ".dds",
        ".bnk", ".bsdiff", ".xdelta",
    }

    def validate_game_root(self, game_root: Path) -> tuple[bool, str]:
        game_root = Path(game_root)
        exe = game_root / "bin64" / "CrimsonDesert.exe"
        papgt = game_root / "meta" / "0.papgt"
        if not game_root.is_dir():
            return False, f"게임 폴더가 없습니다: {game_root}"
        if not exe.is_file():
            return False, f"CrimsonDesert.exe를 찾지 못했습니다: {exe}"
        if not papgt.is_file():
            return False, f"meta/0.papgt를 찾지 못했습니다: {papgt}"
        numbered = [
            child.name for child in game_root.iterdir()
            if child.is_dir() and len(child.name) == 4 and child.name.isdigit()
            and (child / "0.pamt").is_file()
        ]
        if not numbered:
            return False, "0000 형식의 PAZ/PAMT 데이터 폴더를 찾지 못했습니다."
        return True, f"Crimson Desert 게임 구조 확인 완료: {len(numbered)}개 PAZ/PAMT 데이터 폴더"

    def analyze(self, archive_path: Path) -> CrimsonArchiveAnalysis:
        archive_path = Path(archive_path)
        if not archive_path.is_file():
            raise FileNotFoundError(f"모드 파일을 찾을 수 없습니다: {archive_path}")
        suffix = archive_path.suffix.lower()
        nexus_id = self._parse_nexus_mod_id(archive_path.name)
        if suffix != ".zip":
            supported = suffix in self.CDUMM_DIRECT_EXTENSIONS
            return CrimsonArchiveAnalysis(
                archive_path=archive_path,
                valid_archive=supported,
                format_id="cdumm_supported_archive" if supported else "unknown",
                title=archive_path.stem,
                nexus_mod_id=nexus_id,
                notes=(
                    "WorkshopPilot v0.10의 상세 내부 분석은 ZIP을 우선 지원합니다.",
                    "이 파일 형식은 CDUMM에 그대로 전달할 수 있습니다."
                    if supported else "현재 자동 설치 가능한 형식으로 확인하지 못했습니다.",
                ),
            )
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                infos = [x for x in zf.infolist() if not x.is_dir()]
                names = [x.filename.replace("\\", "/") for x in infos]
                exts = tuple(sorted({Path(n).suffix.lower() for n in names if Path(n).suffix}))
                root_prefix = self._common_root_prefix(names)
                manifest_name = self._find_manifest_name(names)
                manifest = {}
                if manifest_name:
                    manifest = json.loads(zf.read(manifest_name).decode("utf-8-sig"))
                    if not isinstance(manifest, dict):
                        raise RuntimeError("manifest.json 최상위 형식이 객체가 아닙니다.")
                fmt = str(manifest.get("format", "") or "").strip()
                title = str(manifest.get("title", "") or "").strip()
                author = str(manifest.get("author", "") or "").strip()
                version = str(manifest.get("version", "") or "").strip()
                description = str(manifest.get("description", "") or "").strip()
                risk = []
                executable_exts = [e for e in exts if e in self.SCRIPT_EXTENSIONS]
                if executable_exts:
                    risk.append("실행 코드 유형이 포함되어 있습니다: " + ", ".join(executable_exts))
                notes = []
                if fmt == "crimson_browser_mod_v1":
                    prefix = f"{root_prefix}/files/" if root_prefix else "files/"
                    if any(n.startswith(prefix) for n in names):
                        notes.append("Crimson Browser 계열 manifest + files/ 구조를 확인했습니다.")
                    else:
                        risk.append("Crimson Browser manifest는 있지만 files/ payload가 없습니다.")
                    notes.append("게임 루트에 단순 복사하지 않고 CDUMM import/apply로 처리합니다.")
                elif manifest_name:
                    notes.append(
                        "manifest.json은 있지만 알려진 Crimson Browser format이 아닙니다: "
                        + (fmt or "(format 없음)")
                    )
                else:
                    known = any(e in {".json", ".paz", ".pamt", ".dds", ".asi", ".bnk", ".bsdiff", ".xdelta", ".cdmod"} for e in exts)
                    if known:
                        fmt = "cdumm_supported_archive"
                        notes.append("Crimson Browser manifest는 없지만 CDUMM 지원 가능성이 높은 payload를 감지했습니다.")
                    else:
                        notes.append("자동 설치 형식을 확정하지 못했습니다. CDUMM GUI에서 수동 검토가 필요합니다.")
                return CrimsonArchiveAnalysis(
                    archive_path=archive_path,
                    valid_archive=True,
                    format_id=fmt or "unknown",
                    title=title or archive_path.stem,
                    author=author,
                    version=version,
                    description=description,
                    nexus_mod_id=nexus_id,
                    root_prefix=root_prefix,
                    file_count=len(infos),
                    total_uncompressed_bytes=sum(x.file_size for x in infos),
                    extensions=exts,
                    risk_flags=tuple(risk),
                    notes=tuple(notes),
                    manifest=manifest,
                )
        except zipfile.BadZipFile as exc:
            raise RuntimeError(f"손상되었거나 ZIP이 아닌 파일입니다: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"manifest.json JSON 파싱 실패: line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc

    @staticmethod
    def _find_manifest_name(names: list[str]) -> str:
        matches = [n for n in names if n.lower() == "manifest.json" or n.lower().endswith("/manifest.json")]
        matches.sort(key=lambda n: (n.count("/"), len(n)))
        return matches[0] if matches else ""

    @staticmethod
    def _common_root_prefix(names: list[str]) -> str:
        if not names:
            return ""
        first = names[0].split("/")[0]
        return first if all(n.startswith(first + "/") for n in names) else ""

    @staticmethod
    def _parse_nexus_mod_id(filename: str) -> str:
        stem = Path(filename).stem
        # Nexus downloads normally end with -<mod id>-<file version>-<unix timestamp>.
        match = re.search(r"-(\d+)-(?:\d+(?:-\d+)*)-(\d{9,})$", stem)
        if match:
            return match.group(1)
        return ""
