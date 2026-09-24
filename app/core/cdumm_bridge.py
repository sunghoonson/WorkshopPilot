from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Callable


class CdummBridge:
    def paths_for(self, game_root: Path) -> dict[str, Path]:
        cdmods = Path(game_root) / "CDMods"
        return {"cdmods": cdmods, "db": cdmods / "cdumm.db", "deltas": cdmods / "deltas", "vanilla": cdmods / "vanilla"}

    def install_archive(self, cdumm_exe: Path, game_root: Path, archive_path: Path, progress: Callable[[str], None] | None = None) -> dict:
        emit = progress or (lambda _text: None)
        game_root = Path(game_root); archive_path = Path(archive_path); paths = self.paths_for(game_root)
        try:
            for key in ("cdmods", "deltas", "vanilla"): paths[key].mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise RuntimeError(
                "Crimson Desert가 Program Files 아래에 있어 CDMods 상태 폴더를 만들 권한이 없습니다. "
                "관리자 실행을 기본 해결책으로 쓰기보다 Steam 라이브러리를 C:\\Games 같은 일반 폴더로 옮기는 방법을 권장합니다."
            ) from exc
        first_snapshot = not self._snapshot_exists(paths["db"])
        if first_snapshot:
            emit("[1/3] 최초 vanilla snapshot을 생성합니다. 게임 아카이브 전체를 읽으므로 시간이 걸릴 수 있습니다.")
            result = self._run_worker(cdumm_exe, ["snapshot", str(game_root), str(paths["db"])], emit)
            if result.get("error"): raise RuntimeError(str(result["error"]))
        else:
            emit("[1/3] 기존 CDUMM vanilla snapshot을 사용합니다.")
        emit(f"[2/3] 모드 import: {archive_path.name}")
        imported = self._run_worker(cdumm_exe, ["import", str(archive_path), str(game_root), str(paths["db"]), str(paths["deltas"])], emit)
        if imported.get("error"):
            if imported.get("needs_script_consent"):
                raise RuntimeError("이 모드는 설치 스크립트 승인이 필요합니다. v0.10은 자동 승인하지 않습니다. CDUMM GUI에서 내용을 확인한 뒤 직접 승인해 주세요.")
            raise RuntimeError(str(imported["error"]))
        emit("[3/3] CDUMM overlay Apply를 실행합니다.")
        applied = self._run_worker(cdumm_exe, ["apply", str(game_root), str(paths["vanilla"]), str(paths["db"]), "0"], emit)
        if applied.get("error"): raise RuntimeError(str(applied["error"]))
        emit("Crimson Desert 모드 적용 완료.")
        return {"snapshot_created": first_snapshot, "import_result": imported, "apply_result": applied, "cdmods_root": str(paths["cdmods"])}

    @staticmethod
    def _snapshot_exists(db_path: Path) -> bool:
        if not db_path.is_file(): return False
        try:
            con = sqlite3.connect(str(db_path))
            try:
                row = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()
                return bool(row and int(row[0]) > 0)
            finally: con.close()
        except sqlite3.Error: return False

    def _run_worker(self, exe: Path, worker_args: list[str], emit: Callable[[str], None]) -> dict:
        kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        if os.name == "nt": kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen([str(exe), "--worker", *worker_args], **kwargs)
        last = {}; errors = []; warnings = []
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.strip()
            if not line: continue
            if not line.startswith("{"):
                emit(f"[CDUMM] {line}"); continue
            try: payload = json.loads(line)
            except json.JSONDecodeError:
                emit(f"[CDUMM] {line}"); continue
            kind = str(payload.get("type", "") or "")
            if kind == "progress":
                pct = payload.get("pct"); msg = str(payload.get("msg", "") or "")
                emit(f"[CDUMM] {str(pct) + '% ' if pct is not None else ''}{msg}")
            elif kind == "warning":
                msg = str(payload.get("msg", "") or ""); warnings.append(msg); emit(f"[CDUMM WARN] {msg}")
            elif kind == "error":
                errors.append(payload); emit(f"[CDUMM ERROR] {payload.get('msg', '')}")
            elif kind == "activity":
                msg = str(payload.get("msg", "") or "")
                if msg: emit(f"[CDUMM] {msg}")
            elif kind == "done": last = payload
            else: last = payload
        rc = proc.wait()
        if errors:
            result = dict(errors[-1]); result["warnings"] = warnings; return result
        if rc != 0: raise RuntimeError(f"CDUMM worker 종료 코드={rc}")
        result = dict(last)
        if warnings: result["warnings"] = warnings
        return result
