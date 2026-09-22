from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.settings import load_settings, save_settings

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WorkshopPilot")
        self.resize(1250, 780)
        self.settings = load_settings()
        self._build_ui()
        self._load_defaults()

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)

        game_row = QHBoxLayout()
        game_row.addWidget(QLabel("게임 / App ID"))
        self.game_edit = QLineEdit()
        self.game_edit.setPlaceholderText("예: RimWorld 또는 294100")
        self.game_search_btn = QPushButton("게임 찾기")
        self.game_search_btn.clicked.connect(self._stub_game_search)
        game_row.addWidget(self.game_edit, 1)
        game_row.addWidget(self.game_search_btn)
        layout.addLayout(game_row)

        steam_row = QHBoxLayout()
        steam_row.addWidget(QLabel("SteamCMD"))
        self.steamcmd_edit = QLineEdit()
        steam_btn = QPushButton("찾기")
        steam_btn.clicked.connect(self._pick_steamcmd)
        steam_row.addWidget(self.steamcmd_edit, 1)
        steam_row.addWidget(steam_btn)
        layout.addLayout(steam_row)

        mods_row = QHBoxLayout()
        mods_row.addWidget(QLabel("Mods 경로"))
        self.mods_edit = QLineEdit()
        mods_btn = QPushButton("찾기")
        mods_btn.clicked.connect(self._pick_mods)
        mods_row.addWidget(self.mods_edit, 1)
        mods_row.addWidget(mods_btn)
        layout.addLayout(mods_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Workshop 검색"))
        self.mod_search_edit = QLineEdit()
        self.mod_search_edit.setPlaceholderText("모드 이름 검색")
        mod_search_btn = QPushButton("검색")
        mod_search_btn.clicked.connect(self._stub_mod_search)
        search_row.addWidget(self.mod_search_edit, 1)
        search_row.addWidget(mod_search_btn)
        layout.addLayout(search_row)

        splitter = QSplitter(Qt.Horizontal)

        self.mod_list = QListWidget()
        self.mod_list.addItem("Workshop 검색 연결 전")
        self.mod_list.addItem("다음 단계에서 결과가 이곳에 표시됩니다.")
        splitter.addWidget(self.mod_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("선택한 모드 상세 정보"))

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlainText(
            "WorkshopPilot 초기 GUI\n\n"
            "예정 기능:\n"
            "- 게임/App ID 검색\n"
            "- Workshop 목록/썸네일\n"
            "- 모드 상세 정보\n"
            "- SteamCMD 다운로드\n"
            "- 지정 Mods 폴더 설치\n"
            "- 다운로드 큐/로그"
        )
        right_layout.addWidget(self.detail, 1)

        download_btn = QPushButton("선택 모드 다운로드 (미구현)")
        download_btn.clicked.connect(
            lambda: self._log("다운로드 기능은 다음 단계에서 QProcess로 연결합니다.")
        )
        right_layout.addWidget(download_btn)

        splitter.addWidget(right)
        splitter.setSizes([500, 700])
        layout.addWidget(splitter, 1)

        layout.addWidget(QLabel("로그"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        layout.addWidget(self.log)

        save_btn = QPushButton("현재 설정 저장")
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        self.setCentralWidget(root)

    def _load_defaults(self) -> None:
        app_id = self.settings.get("active_game", "294100")
        self.game_edit.setText(app_id)
        self.steamcmd_edit.setText(self.settings.get("steamcmd_path", ""))

        game_cfg = self.settings.get("games", {}).get(app_id, {})
        self.mods_edit.setText(
            game_cfg.get("mods_path", r"C:\games\RimWorld\Mods")
        )
        self._log("초기 설정을 불러왔습니다.")

    def _pick_steamcmd(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "steamcmd.exe 선택",
            "",
            "SteamCMD (steamcmd.exe);;실행 파일 (*.exe);;모든 파일 (*)",
        )
        if path:
            self.steamcmd_edit.setText(path)

    def _pick_mods(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Mods 폴더 선택")
        if path:
            self.mods_edit.setText(path)

    def _save_settings(self) -> None:
        app_id = self.game_edit.text().strip() or "294100"
        games = dict(self.settings.get("games", {}))
        game_cfg = dict(games.get(app_id, {}))

        game_cfg["mods_path"] = self.mods_edit.text().strip()
        games[app_id] = game_cfg

        self.settings["steamcmd_path"] = self.steamcmd_edit.text().strip()
        self.settings["active_game"] = app_id
        self.settings["games"] = games
        save_settings(self.settings)
        self._log("config/user_settings.json 에 설정을 저장했습니다.")

    def _stub_game_search(self) -> None:
        self._log(
            f"게임 검색 요청: {self.game_edit.text().strip()!r} "
            "(현재는 UI 초안)"
        )

    def _stub_mod_search(self) -> None:
        self._log(
            "Workshop 검색 요청: "
            f"app_id={self.game_edit.text().strip()}, "
            f"query={self.mod_search_edit.text().strip()!r} "
            "(현재는 UI 초안)"
        )

    def _log(self, text: str) -> None:
        self.log.appendPlainText(text)

def run_app() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    raise SystemExit(app.exec())
