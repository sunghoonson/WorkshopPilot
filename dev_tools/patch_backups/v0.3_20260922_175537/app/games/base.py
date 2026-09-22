from abc import ABC, abstractmethod
from pathlib import Path

class GameAdapter(ABC):
    @abstractmethod
    def validate_mod_folder(self, mod_dir: Path) -> tuple[bool, str]:
        raise NotImplementedError

    def normalize_destination_name(self, workshop_id: str, source_dir: Path) -> str:
        return workshop_id
