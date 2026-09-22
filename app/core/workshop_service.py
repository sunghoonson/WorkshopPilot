from __future__ import annotations

import re
from collections.abc import Iterable

import requests

from app.models.workshop_item import WorkshopItem


class WorkshopService:
    """Search Steam Workshop pages and enrich results with Steam's public details API."""

    BROWSE_URL = "https://steamcommunity.com/workshop/browse/"
    DETAILS_URL = (
        "https://api.steampowered.com/"
        "ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    )
    _ID_PATTERN = re.compile(r"sharedfiles/filedetails/\?id=(\d+)", re.IGNORECASE)

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36 WorkshopPilot/0.2"
                ),
                "Accept-Language": "en-US,en;q=0.8",
            }
        )

    def search(
        self,
        app_id: str,
        query: str = "",
        page: int = 1,
        max_items: int = 30,
    ) -> list[WorkshopItem]:
        app_id = app_id.strip()
        if not app_id.isdigit():
            raise ValueError("App ID는 숫자여야 합니다.")

        params = {
            "appid": app_id,
            "searchtext": query.strip(),
            "browsesort": "textsearch" if query.strip() else "trend",
            "section": "readytouseitems",
            "p": max(1, int(page)),
            "numperpage": max(1, min(int(max_items), 30)),
            "l": "english",
        }

        response = self.session.get(
            self.BROWSE_URL,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()

        published_ids = self._extract_published_file_ids(response.text)
        if not published_ids:
            return []

        details = self.get_details(published_ids[:max_items])
        order = {published_id: i for i, published_id in enumerate(published_ids)}
        details.sort(key=lambda item: order.get(item.published_file_id, 10**9))
        return details

    def get_details(self, published_file_ids: Iterable[str]) -> list[WorkshopItem]:
        ids = [str(value).strip() for value in published_file_ids if str(value).strip()]
        if not ids:
            return []

        results: list[WorkshopItem] = []
        for start in range(0, len(ids), 100):
            chunk = ids[start : start + 100]
            form: dict[str, str | int] = {"itemcount": len(chunk)}
            for index, published_id in enumerate(chunk):
                form[f"publishedfileids[{index}]"] = published_id

            response = self.session.post(
                self.DETAILS_URL,
                data=form,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            raw_items = payload.get("response", {}).get("publishedfiledetails", [])

            for raw in raw_items:
                if int(raw.get("result", 0) or 0) != 1:
                    continue
                published_id = str(raw.get("publishedfileid", "")).strip()
                if not published_id:
                    continue

                tags = []
                for tag in raw.get("tags", []) or []:
                    if isinstance(tag, dict):
                        value = str(tag.get("tag", "")).strip()
                    else:
                        value = str(tag).strip()
                    if value:
                        tags.append(value)

                results.append(
                    WorkshopItem(
                        published_file_id=published_id,
                        title=str(raw.get("title", "") or published_id).strip(),
                        author=str(raw.get("creator", "") or "").strip(),
                        preview_url=str(raw.get("preview_url", "") or "").strip(),
                        description=str(raw.get("description", "") or "").strip(),
                        tags=tags,
                        time_created=self._to_int(raw.get("time_created")),
                        time_updated=self._to_int(raw.get("time_updated")),
                        file_size=self._to_int(raw.get("file_size")),
                        subscriptions=self._to_int(raw.get("subscriptions")),
                        favorited=self._to_int(raw.get("favorited")),
                    )
                )
        return results

    @classmethod
    def _extract_published_file_ids(cls, html: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for match in cls._ID_PATTERN.finditer(html):
            published_id = match.group(1)
            if published_id in seen:
                continue
            seen.add(published_id)
            result.append(published_id)
        return result

    @staticmethod
    def _to_int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
