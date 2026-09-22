from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal


class SteamCmdService(QObject):
    """Run SteamCMD asynchronously and stream its output to the GUI."""

    output_line = Signal(str)
    started = Signal()
    completed = Signal(bool, str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(self.started)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)

        self._buffer = ""
        self._all_output: list[str] = []
        self._steamcmd_exe: Path | None = None
        self._app_id = ""
        self._workshop_id = ""

    @property
    def is_running(self) -> bool:
        return self.process.state() != QProcess.NotRunning

    @staticmethod
    def build_workshop_arguments(
        app_id: str,
        workshop_id: str,
        anonymous: bool = True,
        validate: bool = True,
    ) -> list[str]:
        args: list[str] = []
        if anonymous:
            args += ["+login", "anonymous"]
        args += ["+workshop_download_item", str(app_id), str(workshop_id)]
        if validate:
            args.append("validate")
        args.append("+quit")
        return args

    def download_workshop_item(
        self,
        steamcmd_exe: Path,
        app_id: str,
        workshop_id: str,
    ) -> None:
        if self.is_running:
            raise RuntimeError("SteamCMD가 이미 실행 중입니다.")

        steamcmd_exe = steamcmd_exe.resolve()
        if not steamcmd_exe.is_file():
            raise FileNotFoundError(f"SteamCMD를 찾을 수 없습니다: {steamcmd_exe}")

        self._steamcmd_exe = steamcmd_exe
        self._app_id = str(app_id)
        self._workshop_id = str(workshop_id)
        self._buffer = ""
        self._all_output.clear()

        self.process.setWorkingDirectory(str(steamcmd_exe.parent))
        self.process.setProgram(str(steamcmd_exe))
        self.process.setArguments(
            self.build_workshop_arguments(app_id, workshop_id)
        )
        self.process.start()

    def stop(self) -> None:
        if not self.is_running:
            return
        self.process.terminate()
        if not self.process.waitForFinished(3000):
            self.process.kill()

    def _read_output(self) -> None:
        raw = bytes(self.process.readAllStandardOutput())
        if not raw:
            return
        text = self._decode_output(raw)
        self._buffer += text

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                self._all_output.append(line)
                self.output_line.emit(line)

    def _finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self._read_output()
        if self._buffer.strip():
            line = self._buffer.strip("\r\n")
            self._all_output.append(line)
            self.output_line.emit(line)
        self._buffer = ""

        source = self._content_dir()
        output = "\n".join(self._all_output)
        has_error = bool(
            re.search(
                r"(?:ERROR!|Failed to download|Failure|Access Denied|Invalid platform)",
                output,
                flags=re.IGNORECASE,
            )
        )
        has_content = source.is_dir() and any(source.iterdir())

        success = exit_code == 0 and not has_error and has_content
        if success:
            message = f"Workshop {self._workshop_id} 다운로드 완료"
        elif has_error:
            message = "SteamCMD 출력에서 다운로드 오류를 감지했습니다."
        elif not has_content:
            message = f"다운로드 폴더가 생성되지 않았습니다: {source}"
        else:
            message = f"SteamCMD 종료 코드: {exit_code}"

        self.completed.emit(success, message, str(source))

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            self.completed.emit(False, "SteamCMD 프로세스를 시작하지 못했습니다.", "")

    def _content_dir(self) -> Path:
        if self._steamcmd_exe is None:
            return Path()
        return (
            self._steamcmd_exe.parent
            / "steamapps"
            / "workshop"
            / "content"
            / self._app_id
            / self._workshop_id
        )

    @staticmethod
    def _decode_output(data: bytes) -> str:
        for encoding in ("utf-8", "cp949", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")
