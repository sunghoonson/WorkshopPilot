from dataclasses import dataclass


@dataclass(slots=True)
class GameProfile:
    app_id: str
    name: str
    install_path: str = ""
    mods_path: str = ""
    install_mode: str = "copy_folder"


@dataclass(slots=True)
class GameSearchResult:
    app_id: str
    name: str
    icon_url: str = ""
    logo_url: str = ""
