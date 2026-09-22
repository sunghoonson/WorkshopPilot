from dataclasses import dataclass, field


@dataclass(slots=True)
class WorkshopItem:
    published_file_id: str
    title: str
    author: str = ""
    preview_url: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    installed: bool = False
    time_created: int = 0
    time_updated: int = 0
    file_size: int = 0
    subscriptions: int = 0
    favorited: int = 0

    @property
    def workshop_url(self) -> str:
        return (
            "https://steamcommunity.com/sharedfiles/filedetails/"
            f"?id={self.published_file_id}"
        )
