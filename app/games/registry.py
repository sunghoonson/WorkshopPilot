from __future__ import annotations

from app.games.base import GameAdapter
from app.games.rimworld import RimWorldAdapter


def get_game_adapter(app_id: str) -> GameAdapter | None:
    if str(app_id) == RimWorldAdapter.APP_ID:
        return RimWorldAdapter()
    return None
