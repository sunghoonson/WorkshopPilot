from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path


class DmmManager:
    DOWNLOAD_URL = "https://www.nexusmods.com/crimsondesert/mods/633?tab=files"

    @property
    def managed_root(self) -> Path:
        if os.name == "nt":
            local = os.environ.get("LOCALAPPDATA")
            if local:
                return Path(local) / "WorkshopPilot" / "tools" / "dmm"
        return Path.home() / ".workshoppilot" / "tools" / "dmm"

    @property
    def managed_exe(self) -> Path:
        return self.managed_root / "DMM.exe"

    def resolve(self, external_path: str = "") -> tuple[str, Path] | None:
        if self.managed_exe.is_file():
            return "managed", self.managed_exe
        if external_path:
            candidate = Path(external_path)
            if candidate.is_file() and candidate.suffix.lower() == ".exe":
                return "external", candidate
        return None

    def import_local_package(self, source: Path) -> Path:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f"DMM 파일을 찾을 수 없습니다: {source}")

        self.managed_root.mkdir(parents=True, exist_ok=True)
        temp = self.managed_root / "DMM.exe.part"

        if source.suffix.lower() == ".exe":
            shutil.copy2(source, temp)
        elif source.suffix.lower() == ".zip":
            self._extract_exe_from_zip(source, temp)
        else:
            raise RuntimeError(
                "DMM 가져오기는 .exe 또는 .zip만 지원합니다. "
                "7z/rar이면 먼저 압축을 풀고 DMM.exe를 선택해 주세요."
            )

        if temp.stat().st_size < 1024 * 1024:
            temp.unlink(missing_ok=True)
            raise RuntimeError(
                "선택한 실행 파일이 너무 작아 정상적인 DMM.exe로 보기 어렵습니다."
            )

        try:
            temp.replace(self.managed_exe)
        except PermissionError as exc:
            temp.unlink(missing_ok=True)
            raise RuntimeError(
                "기존 DMM.exe가 실행 중이거나 잠겨 있습니다. "
                "DMM을 종료하고 다시 시도해 주세요."
            ) from exc

        return self.managed_exe

    @staticmethod
    def _extract_exe_from_zip(source: Path, target: Path) -> None:
        names = {"dmm.exe", "definitive-mod-manager.exe"}
        try:
            with zipfile.ZipFile(source, "r") as zf:
                files = [x for x in zf.infolist() if not x.is_dir()]
                matches = [
                    x for x in files
                    if Path(x.filename).name.lower() in names
                ]
                if not matches:
                    matches = [
                        x for x in files
                        if Path(x.filename).suffix.lower() == ".exe"
                        and "dmm" in Path(x.filename).name.lower()
                    ]
                if len(matches) != 1:
                    found = ", ".join(Path(x.filename).name for x in matches) or "없음"
                    raise RuntimeError(
                        "ZIP에서 DMM 실행 파일을 하나로 확정하지 못했습니다. "
                        f"감지 결과: {found}"
                    )
                with zf.open(matches[0], "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile as exc:
            raise RuntimeError(f"손상된 ZIP입니다: {exc}") from exc
