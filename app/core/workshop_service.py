from __future__ import annotations

from app.models.workshop_item import WorkshopItem

class WorkshopService:
    """Steam Workshop 탐색 계층의 초기 인터페이스."""

    def search(
        self,
        app_id: str,
        query: str = "",
        page: int = 1,
    ) -> list[WorkshopItem]:
        # 다음 단계에서 실제 Workshop 조회 연결
        return []
