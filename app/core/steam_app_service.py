from __future__ import annotations

from urllib.parse import quote

import requests

from app.models.game import GameSearchResult


class SteamAppService:
    """Public Steam endpoints used to resolve a game name or App ID."""

    SEARCH_URL = "https://steamcommunity.com/actions/SearchApps/{query}"
    DETAILS_URL = "https://store.steampowered.com/api/appdetails"

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36 WorkshopPilot/0.2"
                )
            }
        )

    def search(self, query: str, limit: int = 20) -> list[GameSearchResult]:
        query = query.strip()
        if not query:
            return []

        if query.isdigit():
            return [self._lookup_app_id(query)]

        url = self.SEARCH_URL.format(query=quote(query, safe=""))
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()

        results: list[GameSearchResult] = []
        for raw in payload[:limit]:
            app_id = str(raw.get("appid", "")).strip()
            name = str(raw.get("name", "")).strip()
            if not app_id or not name:
                continue
            results.append(
                GameSearchResult(
                    app_id=app_id,
                    name=name,
                    icon_url=str(raw.get("icon", "") or ""),
                    logo_url=str(raw.get("logo", "") or ""),
                )
            )
        return results

    def _lookup_app_id(self, app_id: str) -> GameSearchResult:
        response = self.session.get(
            self.DETAILS_URL,
            params={"appids": app_id, "l": "english", "cc": "us"},
            timeout=self.timeout,
        )
        response.raise_for_status()

        payload = response.json().get(app_id, {})
        data = payload.get("data", {}) if payload.get("success") else {}
        name = str(data.get("name", "") or f"App {app_id}")
        header = str(data.get("header_image", "") or "")
        return GameSearchResult(app_id=app_id, name=name, logo_url=header)
