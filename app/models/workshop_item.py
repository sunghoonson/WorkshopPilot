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
