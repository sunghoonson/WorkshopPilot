from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.steamcmd_service import SteamCmdService


def main() -> int:
    anon = SteamCmdService.build_workshop_arguments(
        "294100", "2009463077", auth_mode="anonymous"
    )
    assert anon[:2] == ["+login", "anonymous"]

    account = SteamCmdService.build_workshop_arguments(
        "294100", "2009463077", auth_mode="account", username="example_user"
    )
    assert account[:2] == ["+login", "example_user"]
    assert "password" not in " ".join(account).lower()

    assert SteamCmdService._looks_like_auth_required(
        "ERROR! Failed to download item 1 (Access Denied)"
    )
    assert not SteamCmdService._looks_like_auth_required(
        "ERROR! Failed to download item 1 (Timeout)"
    )

    print("[OK] Steam auth logic smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
