from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.steamcmd_manager import SteamCmdManager
from app.core.steamcmd_service import SteamCmdService


KOREAN_BOOTSTRAP = """
[ 95%] 업데이트 다운로드 중...(43,472/43,472KB)
[100%] 다운로드 완료.
[----] 업데이트 설치 중...
[----] 삭제 중...
[----] 업데이트 완료! Steam 실행 중...
"""

ENGLISH_BOOTSTRAP = """
[----] Installing update...
[----] Cleaning up...
[----] Update complete, launching...
"""


def main() -> int:
    assert SteamCmdManager._is_self_update_restart(7, KOREAN_BOOTSTRAP)
    assert SteamCmdService._is_self_update_restart(7, KOREAN_BOOTSTRAP)

    assert SteamCmdManager._is_self_update_restart(7, ENGLISH_BOOTSTRAP)
    assert SteamCmdService._is_self_update_restart(7, ENGLISH_BOOTSTRAP)

    assert not SteamCmdManager._is_self_update_restart(
        7, "ERROR! Failed to install app (Access Denied)"
    )
    assert not SteamCmdService._is_self_update_restart(
        7, "ERROR! Failed to install app (Access Denied)"
    )

    assert not SteamCmdManager._is_self_update_restart(1, KOREAN_BOOTSTRAP)
    assert not SteamCmdService._is_self_update_restart(1, KOREAN_BOOTSTRAP)

    print("[OK] Korean/English SteamCMD bootstrap detection passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
