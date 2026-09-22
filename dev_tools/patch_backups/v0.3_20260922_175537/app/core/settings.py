from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_SETTINGS = CONFIG_DIR / "defaults.json"
USER_SETTINGS = CONFIG_DIR / "user_settings.json"

def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def load_settings() -> dict:
    defaults = _read_json(DEFAULT_SETTINGS)
    user = _read_json(USER_SETTINGS)

    merged = dict(defaults)
    merged.update(user)

    if "games" in defaults or "games" in user:
        merged["games"] = dict(defaults.get("games", {}))
        merged["games"].update(user.get("games", {}))

    return merged

def save_settings(settings: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with USER_SETTINGS.open("w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
