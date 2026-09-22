from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class SteamCmdService(QObject):
    """
    Run SteamCMD asynchronously and stream output to the GUI.

    Authentication modes:
      - auto: try anonymous first; offer account retry only on auth-like failure
      - anonymous: always `login anonymous`
      - account: `login <username>` and answer password/Steam Guard prompts via stdin

    Passwords and Steam Guard codes are never persisted by this class.
    """

    output_line = Signal(str)
    started = Signal()
    completed = Signal(bool, str, str)

    # kind: "password" | "guard"
    credential_required = Signal(str, str)

    # Emitted only when auto mode used anonymous first and the output looks like
    # an authentication/ownership failure.
    auth_fallback_required = Signal(str)

    MAX_SELF_UPDATE_RETRIES = 3

    AUTH_MODES = {"auto", "anonymous", "account"}

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
        self._prompt_tail = ""

        self._steamcmd_exe: Path | None = None
        self._app_id = ""
        self._workshop_id = ""
        self._arguments: list[str] = []

        self._auth_mode = "anonymous"
        self._attempt_mode = "anonymous"
        self._username = ""

        self._self_update_retries = 0
        self._completion_emitted = False
        self._abort_message = ""

        self._password_prompt_pending = False
        self._guard_prompt_pending = False
        self._password_prompt_count = 0
        self._guard_prompt_count = 0

    @property
    def is_running(self) -> bool:
        return self.process.state() != QProcess.NotRunning

    @staticmethod
    def build_workshop_arguments(
        app_id: str,
        workshop_id: str,
        auth_mode: str = "anonymous",
        username: str = "",
        validate: bool = True,
    ) -> list[str]:
        auth_mode = (auth_mode or "anonymous").strip().lower()
        args: list[str] = []

        if auth_mode == "account":
            username = username.strip()
            if not username:
                raise ValueError("Steam 계정 로그인을 사용하려면 계정명이 필요합니다.")
            # Do not put the password on the command line. SteamCMD will prompt,
            # then WorkshopPilot writes the response through QProcess stdin.
            args += ["+login", username]
        else:
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
        auth_mode: str = "auto",
        username: str = "",
    ) -> None:
        if self.is_running:
            raise RuntimeError("SteamCMD가 이미 실행 중입니다.")

        steamcmd_exe = steamcmd_exe.resolve()
        if not steamcmd_exe.is_file():
            raise FileNotFoundError(f"SteamCMD를 찾을 수 없습니다: {steamcmd_exe}")

        auth_mode = (auth_mode or "auto").strip().lower()
        if auth_mode not in self.AUTH_MODES:
            raise ValueError(f"지원하지 않는 Steam 인증 방식입니다: {auth_mode}")

        self._steamcmd_exe = steamcmd_exe
        self._app_id = str(app_id)
        self._workshop_id = str(workshop_id)
        self._auth_mode = auth_mode
        self._attempt_mode = "anonymous" if auth_mode == "auto" else auth_mode
        self._username = username.strip()

        self._self_update_retries = 0
        self._completion_emitted = False
        self._abort_message = ""

        self._prepare_attempt(self._attempt_mode)
        self._start_attempt()

    def retry_with_account(self, username: str) -> None:
        """
        Continue the same pending Workshop download with an authenticated account.

        This is intended for auto-mode fallback after an anonymous auth failure.
        """
        if self.is_running:
            raise RuntimeError("SteamCMD가 아직 종료되지 않았습니다.")

        username = username.strip()
        if not username:
            raise ValueError("Steam 계정명이 필요합니다.")

        self._username = username
        self._attempt_mode = "account"
        self._self_update_retries = 0
        self._completion_emitted = False
        self._abort_message = ""

        self._prepare_attempt("account")
        QTimer.singleShot(100, self._start_attempt)

    def submit_credential(self, kind: str, value: str) -> None:
        """
        Send a password or Steam Guard code to the running SteamCMD process.

        The value is used only for the current process interaction and is not saved.
        """
        if not self.is_running:
            raise RuntimeError("SteamCMD가 실행 중이 아닙니다.")

        kind = kind.strip().lower()
        if kind not in {"password", "guard"}:
            raise ValueError(f"알 수 없는 인증 입력 종류입니다: {kind}")

        payload = (value + "\n").encode("utf-8")
        written = self.process.write(payload)
        if written < 0:
            raise RuntimeError("SteamCMD 표준 입력에 인증 정보를 전달하지 못했습니다.")

        if kind == "password":
            self._password_prompt_pending = False
        else:
            self._guard_prompt_pending = False

    def cancel_current(self, message: str = "사용자가 Steam 인증을 취소했습니다.") -> None:
        self._abort_message = message
        if self.is_running:
            self.process.kill()
        else:
            self._emit_completed_once(False, message, "")

    def fail_pending_auth(self, message: str) -> None:
        """
        Finish an auto-mode fallback that was declined by the user.
        No process is running at this point.
        """
        self._emit_completed_once(False, message, str(self._content_dir()))

    def _prepare_attempt(self, actual_auth_mode: str) -> None:
        self._arguments = self.build_workshop_arguments(
            self._app_id,
            self._workshop_id,
            auth_mode=actual_auth_mode,
            username=self._username,
        )
        self._reset_attempt_output()

    def _start_attempt(self) -> None:
        if self._steamcmd_exe is None:
            self._emit_completed_once(False, "SteamCMD 실행 경로가 설정되지 않았습니다.", "")
            return

        self.process.setWorkingDirectory(str(self._steamcmd_exe.parent))
        self.process.setProgram(str(self._steamcmd_exe))
        self.process.setArguments(self._arguments)
        self.process.start()

    def _reset_attempt_output(self) -> None:
        self._buffer = ""
        self._all_output.clear()
        self._prompt_tail = ""
        self._password_prompt_pending = False
        self._guard_prompt_pending = False
        self._password_prompt_count = 0
        self._guard_prompt_count = 0

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
        self._detect_credential_prompts(text)
        self._buffer += text

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                self._all_output.append(line)
                self.output_line.emit(line)

    def _detect_credential_prompts(self, text: str) -> None:
        """
        SteamCMD prompts are not guaranteed to end in a newline.
        Keep a small tail so prompts split across QProcess chunks are detectable.
        """
        scan = (self._prompt_tail + text)[-800:]
        lower = scan.lower()

        password_patterns = (
            r"password\s*:\s*$",
            r"steam password\s*:\s*$",
            r"passphrase\s*:\s*$",
        )
        guard_patterns = (
            r"steam guard(?: code)?\s*:\s*$",
            r"two[- ]factor(?: code)?\s*:\s*$",
            r"auth(?:entication)? code\s*:\s*$",
            r"guard code\s*:\s*$",
        )

        password_hits = sum(
            1 for pattern in password_patterns if re.search(pattern, lower, flags=re.I | re.M)
        )
        guard_hits = sum(
            1 for pattern in guard_patterns if re.search(pattern, lower, flags=re.I | re.M)
        )

        # A guard prompt may contain the word "password" in surrounding help text.
        if guard_hits and not self._guard_prompt_pending:
            self._guard_prompt_count += 1
            self._guard_prompt_pending = True
            self.credential_required.emit(
                "guard",
                "Steam Guard / 2단계 인증 코드를 입력해 주세요.",
            )
        elif password_hits and not self._password_prompt_pending:
            self._password_prompt_count += 1
            self._password_prompt_pending = True
            self.credential_required.emit(
                "password",
                "Steam 계정 비밀번호를 입력해 주세요.",
            )

        self._prompt_tail = scan[-160:]

    def _finished(
        self,
        exit_code: int,
        _exit_status: QProcess.ExitStatus,
    ) -> None:
        self._read_output()

        if self._buffer.strip():
            line = self._buffer.strip("\r\n")
            self._all_output.append(line)
            self.output_line.emit(line)

        self._buffer = ""
        output = "\n".join(self._all_output)

        if self._abort_message:
            message = self._abort_message
            self._abort_message = ""
            self._emit_completed_once(False, message, "")
            return

        if self._is_self_update_restart(exit_code, output):
            if self._self_update_retries < self.MAX_SELF_UPDATE_RETRIES:
                self._self_update_retries += 1
                self.output_line.emit(
                    "[WorkshopPilot] SteamCMD 자체 업데이트 완료. "
                    f"명령을 자동 재실행합니다 "
                    f"({self._self_update_retries}/{self.MAX_SELF_UPDATE_RETRIES})."
                )
                self._reset_attempt_output()
                QTimer.singleShot(1500, self._start_attempt)
                return

            self._emit_completed_once(
                False,
                "SteamCMD가 자체 업데이트 후 반복해서 재시작을 요청했습니다.",
                str(self._content_dir()),
            )
            return

        source = self._content_dir()

        auth_required = self._looks_like_auth_required(output)
        if (
            self._auth_mode == "auto"
            and self._attempt_mode == "anonymous"
            and auth_required
        ):
            self.auth_fallback_required.emit(
                "익명 Steam 로그인으로 Workshop 다운로드가 거부되었습니다. "
                "이 게임/항목은 Steam 계정 인증이나 게임 소유권을 요구할 수 있습니다."
            )
            return

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
            mode_text = "계정" if self._attempt_mode == "account" else "익명"
            message = (
                f"Workshop {self._workshop_id} 다운로드 완료 "
                f"(Steam 인증: {mode_text})"
            )
        elif auth_required:
            message = (
                "Steam 인증 또는 게임 소유권이 필요한 것으로 보입니다. "
                "인증 방식을 'Steam 계정' 또는 '자동'으로 변경해 다시 시도해 주세요."
            )
        elif has_error:
            message = "SteamCMD 출력에서 다운로드 오류를 감지했습니다."
        elif not has_content:
            message = f"다운로드 폴더가 생성되지 않았습니다: {source}"
        else:
            message = f"SteamCMD 종료 코드: {exit_code}"

        self._emit_completed_once(success, message, str(source))

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            self._emit_completed_once(
                False,
                "SteamCMD 프로세스를 시작하지 못했습니다.",
                "",
            )

    def _emit_completed_once(self, success: bool, message: str, source: str) -> None:
        if self._completion_emitted:
            return
        self._completion_emitted = True
        self.completed.emit(success, message, source)

    @staticmethod
    def _is_self_update_restart(exit_code: int, output: str) -> bool:
        text = output.lower()
        update_marker = (
            "update complete, launching" in text
            or "restarting steamcmd by request" in text
        )
        return exit_code == 7 and update_marker

    @staticmethod
    def _looks_like_auth_required(output: str) -> bool:
        text = output.lower()
        patterns = (
            "access denied",
            "no subscription",
            "does not own",
            "doesn't own",
            "requires ownership",
            "account logon denied",
            "login failure",
            "not logged on",
            "please login",
            "must be logged",
            "authentication required",
        )
        return any(pattern in text for pattern in patterns)

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
