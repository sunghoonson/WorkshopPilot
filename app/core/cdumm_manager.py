from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Callable

import requests


class CdummManager:
    LATEST_RELEASE_API = (
        "https://api.github.com/repos/"
        "faisalkindi/CrimsonDesert-UltimateModsManager/releases/latest"
    )
    USER_AGENT = "WorkshopPilot/0.10"

    @property
    def managed_root(self) -> Path:
        if os.name == "nt":
            local = os.environ.get("LOCALAPPDATA")
            if local:
                return Path(local) / "WorkshopPilot" / "tools" / "cdumm"
        return Path.home() / ".workshoppilot" / "tools" / "cdumm"

    @property
    def managed_exe(self) -> Path:
        return self.managed_root / "CDUMM3.exe"

    def resolve(self, external_path: str = "") -> tuple[str, Path] | None:
        if self.managed_exe.is_file():
            return "managed", self.managed_exe
        if external_path:
            p = Path(external_path)
            if p.is_file():
                return "external", p
        return None

    def install_or_update(self, progress: Callable[[str], None] | None = None) -> Path:
        emit = progress or (lambda _text: None)
        session = requests.Session()
        session.headers.update({"User-Agent": self.USER_AGENT, "Accept": "application/vnd.github+json"})
        emit("GitHub에서 최신 CDUMM 릴리스 정보를 확인합니다.")
        response = session.get(self.LATEST_RELEASE_API, timeout=30)
        response.raise_for_status()
        release = response.json()
        asset = self._pick_windows_asset(release)
        if asset is None:
            raise RuntimeError("최신 CDUMM 릴리스에서 CDUMM3.exe 자산을 찾지 못했습니다.")
        url = str(asset.get("browser_download_url", "") or "")
        tag = str(release.get("tag_name", "") or "")
        if not url:
            raise RuntimeError("CDUMM 다운로드 URL이 비어 있습니다.")
        self.managed_root.mkdir(parents=True, exist_ok=True)
        temp = self.managed_exe.with_suffix(".exe.part")
        emit(f"CDUMM {tag or '(latest)'} 다운로드를 시작합니다.")
        hasher = hashlib.sha256()
        with session.get(url, stream=True, timeout=(30, 180)) as dl:
            dl.raise_for_status()
            total = int(dl.headers.get("Content-Length", "0") or 0)
            received = 0
            with temp.open("wb") as f:
                for chunk in dl.iter_content(1024 * 1024):
                    if not chunk: continue
                    f.write(chunk); hasher.update(chunk); received += len(chunk)
                    if total:
                        emit(f"CDUMM 다운로드: {int(received * 100 / total)}%")
                    else:
                        emit(f"CDUMM 다운로드: {received / (1024 * 1024):.1f} MB")
        digest = str(asset.get("digest", "") or "")
        if digest.lower().startswith("sha256:"):
            expected = digest.split(":", 1)[1].strip().lower()
            if expected and expected != hasher.hexdigest().lower():
                temp.unlink(missing_ok=True)
                raise RuntimeError("CDUMM 다운로드 SHA-256 검증에 실패했습니다.")
            emit("CDUMM SHA-256 검증 완료.")
        try:
            temp.replace(self.managed_exe)
        except PermissionError as exc:
            temp.unlink(missing_ok=True)
            raise RuntimeError("기존 CDUMM3.exe가 실행 중이거나 잠겨 있습니다. CDUMM을 종료한 뒤 다시 시도해 주세요.") from exc
        (self.managed_root / "release.json").write_text(
            json.dumps({"tag_name": tag, "asset_name": asset.get("name"), "sha256": hasher.hexdigest()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        emit("CDUMM headless self-check를 실행합니다.")
        status = self.self_check(self.managed_exe)
        if not status.get("ok", False):
            raise RuntimeError("CDUMM self-check 실패: " + json.dumps(status, ensure_ascii=False))
        emit("관리형 CDUMM 준비 완료.")
        return self.managed_exe

    def self_check(self, exe: Path) -> dict:
        kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=90)
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run([str(exe), "--worker", "self_check"], **kwargs)
        done = {}
        for raw in (proc.stdout or "").splitlines():
            line = raw.strip()
            if not line.startswith("{"): continue
            try: item = json.loads(line)
            except json.JSONDecodeError: continue
            if item.get("type") == "done": done = item
        if proc.returncode != 0 and not done:
            raise RuntimeError(f"CDUMM self-check 종료 코드={proc.returncode}\n{(proc.stdout or '').strip()}")
        return done

    @staticmethod
    def _pick_windows_asset(release: dict) -> dict | None:
        assets = list(release.get("assets", []) or [])
        for asset in assets:
            if str(asset.get("name", "") or "").lower() == "cdumm3.exe": return asset
        for asset in assets:
            name = str(asset.get("name", "") or "").lower()
            if name.endswith(".exe") and "cdumm" in name: return asset
        return None
