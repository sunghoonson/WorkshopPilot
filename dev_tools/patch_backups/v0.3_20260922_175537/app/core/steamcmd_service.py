from __future__ import annotations

from pathlib import Path

class SteamCmdService:
    """SteamCMD 실행 계층. 실제 GUI 실행은 QProcess로 연결 예정."""

    @staticmethod
    def build_workshop_command(
        steamcmd_exe: str,
        app_id: str,
        workshop_id: str,
        anonymous: bool = True,
    ) -> list[str]:
        exe = str(Path(steamcmd_exe))
        login = ["+login", "anonymous"] if anonymous else []
        return [
            exe,
            *login,
            "+workshop_download_item",
            str(app_id),
            str(workshop_id),
            "+quit",
        ]
