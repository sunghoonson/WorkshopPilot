from __future__ import annotations

import os
import platform
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Callable

import requests


ProgressCallback = Callable[[str], None]


class SteamCmdManager:
    """Install, repair, and resolve the SteamCMD runtime used by WorkshopPilot."""

    DOWNLOAD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    @property
    def app_data_root(self) -> Path:
        if os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                return Path(local_app_data) / "WorkshopPilot"
            return Path.home() / "AppData" / "Local" / "WorkshopPilot"
        return Path.home() / ".local" / "share" / "WorkshopPilot"

    @property
    def managed_root(self) -> Path:
        return self.app_data_root / "tools" / "steamcmd"

    @property
    def managed_exe(self) -> Path:
        return self.managed_root / ("steamcmd.exe" if os.name == "nt" else "steamcmd.sh")

    def resolve(self, configured_external: str = "") -> tuple[str, Path] | None:
        """Return (mode, executable) preferring WorkshopPilot-managed SteamCMD."""
        if self.managed_exe.is_file():
            return "managed", self.managed_exe

        external = Path(configured_external.strip()) if configured_external.strip() else None
        if external and external.is_file():
            return "external", external

        return None

    def install_or_repair(self, progress: ProgressCallback | None = None) -> Path:
        if os.name != "nt":
            raise RuntimeError("현재 자동 SteamCMD 설치는 Windows만 지원합니다.")

        self.managed_root.mkdir(parents=True, exist_ok=True)
        zip_path = self.managed_root / "steamcmd_download.zip.part"

        self._emit(progress, "Valve 서버에서 SteamCMD 다운로드를 시작합니다.")
        self._download(zip_path, progress)
        self._emit(progress, "SteamCMD 압축을 해제합니다.")
        self._safe_extract(zip_path, self.managed_root)
        zip_path.unlink(missing_ok=True)

        if not self.managed_exe.is_file():
            raise RuntimeError(f"steamcmd.exe를 찾지 못했습니다: {self.managed_exe}")

        self._emit(progress, "SteamCMD 최초 초기화/업데이트를 실행합니다.")
        completed = subprocess.run(
            [str(self.managed_exe), "+quit"],
            cwd=str(self.managed_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            timeout=300,
            check=False,
        )

        if completed.returncode != 0:
            output = self._decode_output(completed.stdout or b"")
            tail = "\n".join(output.splitlines()[-12:])
            raise RuntimeError(
                "SteamCMD 초기화에 실패했습니다. "
                f"종료 코드={completed.returncode}\n{tail}"
            )

        self._emit(progress, f"SteamCMD 준비 완료: {self.managed_exe}")
        return self.managed_exe

    def clear_managed_runtime(self) -> None:
        if self.managed_root.exists():
            shutil.rmtree(self.managed_root)

    def workshop_content_dir(self, steamcmd_exe: Path, app_id: str, workshop_id: str) -> Path:
        return (
            steamcmd_exe.parent
            / "steamapps"
            / "workshop"
            / "content"
            / str(app_id)
            / str(workshop_id)
        )

    def _download(self, destination: Path, progress: ProgressCallback | None) -> None:
        with requests.get(
            self.DOWNLOAD_URL,
            stream=True,
            timeout=self.timeout,
            headers={"User-Agent": "WorkshopPilot/0.3"},
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            received = 0
            last_percent = -1

            with destination.open("wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    received += len(chunk)

                    if total > 0:
                        percent = min(100, int(received * 100 / total))
                        if percent != last_percent and (percent % 5 == 0 or percent == 100):
                            self._emit(progress, f"SteamCMD 다운로드: {percent}%")
                            last_percent = percent

        if not destination.is_file() or destination.stat().st_size <= 0:
            raise RuntimeError("SteamCMD ZIP 다운로드 결과가 비어 있습니다.")

    @staticmethod
    def _safe_extract(zip_path: Path, destination: Path) -> None:
        destination = destination.resolve()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                candidate = (destination / member.filename).resolve()
                try:
                    candidate.relative_to(destination)
                except ValueError as exc:
                    raise RuntimeError(f"안전하지 않은 ZIP 경로: {member.filename}") from exc
            zf.extractall(destination)

    @staticmethod
    def _emit(callback: ProgressCallback | None, text: str) -> None:
        if callback is not None:
            callback(text)

    @staticmethod
    def _decode_output(data: bytes) -> str:
        for encoding in ("utf-8", "cp949", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")
