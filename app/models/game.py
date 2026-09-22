from dataclasses import dataclass

@dataclass(slots=True)
class GameProfile:
    app_id: str
    name: str
    install_path: str = ""
    mods_path: str = ""
    install_mode: str = "copy_folder"
