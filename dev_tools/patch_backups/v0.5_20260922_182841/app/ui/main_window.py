from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.installer import install_mod_folder
from app.core.settings import load_settings, save_settings
from app.core.steam_app_service import SteamAppService
from app.core.steamcmd_manager import SteamCmdManager
from app.core.steamcmd_service import SteamCmdService
from app.core.workshop_service import WorkshopService
from app.games.registry import get_game_adapter
from app.models.game import GameSearchResult
from app.models.workshop_item import WorkshopItem


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(str)


class FunctionWorker(QRunnable):
    def __init__(
        self,
        fn: Callable[[], Any] | None = None,
        progress_fn: Callable[[Callable[[str], None]], Any] | None = None,
    ) -> None:
        super().__init__()
        self.fn = fn
        self.progress_fn = progress_fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            if self.progress_fn is not None:
                result = self.progress_fn(self.signals.progress.emit)
            elif self.fn is not None:
                result = self.fn()
            else:
                result = None
        except Exception as exc:
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.succeeded.emit(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WorkshopPilot")
        self.resize(1320, 840)

        self.settings = load_settings()
        self.app_service = SteamAppService()
        self.workshop_service = WorkshopService()
        self.steamcmd_manager = SteamCmdManager()
        self.steamcmd_service = SteamCmdService(self)
        self.thread_pool = QThreadPool.globalInstance()
        self.network = QNetworkAccessManager(self)

        self.current_game_name = ""
        self.workshop_items: dict[str, WorkshopItem] = {}
        self.pixmap_cache: dict[str, QPixmap] = {}
        self._thumbnail_generation = 0
        self._active_workers: set[FunctionWorker] = set()
        self._pending_download_id = ""
        self._active_download_id = ""
        self._active_download_app_id = ""
        self._active_mods_root = ""

        self._build_ui()
        self._connect_steamcmd_signals()
        self._load_defaults()

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)

        game_row = QHBoxLayout()
        game_row.addWidget(QLabel("게임 / App ID"))
        self.game_edit = QLineEdit()
        self.game_edit.setPlaceholderText("예: RimWorld 또는 294100")
        self.game_edit.returnPressed.connect(self._search_game)
        self.game_search_btn = QPushButton("게임 찾기")
        self.game_search_btn.clicked.connect(self._search_game)
        self.game_name_label = QLabel("")
        self.game_name_label.setMinimumWidth(180)
        game_row.addWidget(self.game_edit, 1)
        game_row.addWidget(self.game_name_label)
        game_row.addWidget(self.game_search_btn)
        layout.addLayout(game_row)

        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel("Steam 도구"))
        self.steam_status_label = QLabel("확인 중...")
        self.steam_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.install_steamcmd_btn = QPushButton("내장 설치/복구")
        self.install_steamcmd_btn.clicked.connect(self._install_managed_steamcmd)
        self.external_steamcmd_btn = QPushButton("외부 도구 선택")
        self.external_steamcmd_btn.clicked.connect(self._pick_external_steamcmd)
        tool_row.addWidget(self.steam_status_label, 1)
        tool_row.addWidget(self.install_steamcmd_btn)
        tool_row.addWidget(self.external_steamcmd_btn)
        layout.addLayout(tool_row)

        auth_row = QHBoxLayout()
        auth_row.addWidget(QLabel("Steam 인증"))
        self.auth_mode_combo = QComboBox()
        self.auth_mode_combo.addItem("자동 (익명 우선)", "auto")
        self.auth_mode_combo.addItem("익명", "anonymous")
        self.auth_mode_combo.addItem("Steam 계정", "account")
        self.auth_mode_combo.currentIndexChanged.connect(self._on_auth_mode_changed)

        self.steam_username_edit = QLineEdit()
        self.steam_username_edit.setPlaceholderText(
            "Steam 계정명 (자동 fallback / 계정 모드에서 사용)"
        )
        self.auth_security_label = QLabel("비밀번호/Steam Guard 코드는 저장하지 않음")
        self.auth_security_label.setStyleSheet("QLabel { color: #777; }")

        auth_row.addWidget(self.auth_mode_combo)
        auth_row.addWidget(self.steam_username_edit, 1)
        auth_row.addWidget(self.auth_security_label)
        layout.addLayout(auth_row)

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
        self.mod_search_edit.setPlaceholderText("예: Harmony / Camera / Korean")
        self.mod_search_edit.returnPressed.connect(self._search_mods)
        self.mod_search_btn = QPushButton("검색")
        self.mod_search_btn.clicked.connect(self._search_mods)
        self.result_count_label = QLabel("")
        search_row.addWidget(self.mod_search_edit, 1)
        search_row.addWidget(self.result_count_label)
        search_row.addWidget(self.mod_search_btn)
        layout.addLayout(search_row)

        splitter = QSplitter(Qt.Horizontal)

        self.mod_list = QListWidget()
        self.mod_list.setIconSize(QSize(96, 96))
        self.mod_list.setSpacing(3)
        self.mod_list.currentItemChanged.connect(self._on_mod_selected)
        splitter.addWidget(self.mod_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.preview_label = QLabel("미리보기")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(210)
        self.preview_label.setStyleSheet(
            "QLabel { background: #1f1f1f; color: #aaaaaa; border: 1px solid #555; }"
        )
        right_layout.addWidget(self.preview_label)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("검색 결과를 선택하면 상세 정보가 표시됩니다.")
        right_layout.addWidget(self.detail, 1)

        button_row = QHBoxLayout()
        self.open_workshop_btn = QPushButton("Workshop 페이지 열기")
        self.open_workshop_btn.setEnabled(False)
        self.open_workshop_btn.clicked.connect(self._open_selected_workshop)
        self.download_btn = QPushButton("선택 모드 다운로드 / 설치")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._download_selected_mod)
        button_row.addWidget(self.open_workshop_btn)
        button_row.addWidget(self.download_btn, 1)
        right_layout.addLayout(button_row)

        splitter.addWidget(right)
        splitter.setSizes([520, 780])
        layout.addWidget(splitter, 1)

        layout.addWidget(QLabel("로그"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setMaximumHeight(190)
        layout.addWidget(self.log)

        save_btn = QPushButton("현재 설정 저장")
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        self.setCentralWidget(root)

    def _connect_steamcmd_signals(self) -> None:
        self.steamcmd_service.started.connect(
            lambda: self._log("INFO", "SteamCMD 프로세스가 시작되었습니다.")
        )
        self.steamcmd_service.output_line.connect(
            lambda line: self._log("STEAM", line)
        )
        self.steamcmd_service.completed.connect(self._on_steamcmd_completed)
        self.steamcmd_service.credential_required.connect(
            self._on_steam_credential_required
        )
        self.steamcmd_service.auth_fallback_required.connect(
            self._on_auth_fallback_required
        )

    def _load_defaults(self) -> None:
        app_id = self.settings.get("active_game", "294100")
        self.game_edit.setText(app_id)

        game_cfg = self.settings.get("games", {}).get(app_id, {})
        self.current_game_name = str(game_cfg.get("name", ""))
        self.game_name_label.setText(self.current_game_name)
        self.mods_edit.setText(game_cfg.get("mods_path", r"C:\games\RimWorld\Mods"))

        auth_mode = str(self.settings.get("steam_auth_mode", "auto") or "auto")
        index = self.auth_mode_combo.findData(auth_mode)
        self.auth_mode_combo.setCurrentIndex(index if index >= 0 else 0)
        self.steam_username_edit.setText(
            str(self.settings.get("steam_username", "") or "")
        )
        self._on_auth_mode_changed()

        self._refresh_steam_tool_status()
        self._log("INFO", "초기 설정을 불러왔습니다.")

    def _refresh_steam_tool_status(self) -> None:
        resolved = self.steamcmd_manager.resolve(
            str(self.settings.get("steamcmd_path", "") or "")
        )
        if resolved is None:
            if self.steamcmd_manager.managed_exe.is_file():
                self.steam_status_label.setText(
                    "△ SteamCMD 파일 있음 — 초기화/복구 필요"
                )
                self.steam_status_label.setToolTip(
                    "steamcmd.exe는 존재하지만 WorkshopPilot 준비 확인이 끝나지 않았습니다.\n"
                    f"관리형 위치: {self.steamcmd_manager.managed_root}"
                )
            else:
                self.steam_status_label.setText(
                    "○ 설치되지 않음 — 다운로드 시 자동 설치 가능"
                )
                self.steam_status_label.setToolTip(
                    f"관리형 설치 위치: {self.steamcmd_manager.managed_root}"
                )
            return

        mode, path = resolved
        mode_text = "관리형" if mode == "managed" else "외부"
        self.steam_status_label.setText(f"● 준비됨 ({mode_text})")
        self.steam_status_label.setToolTip(str(path))

    def _pick_external_steamcmd(self) -> None:
        current = str(self.settings.get("steamcmd_path", "") or "")
        start_dir = str(Path(current).parent) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "외부 steamcmd.exe 선택",
            start_dir,
            "SteamCMD (steamcmd.exe);;실행 파일 (*.exe);;모든 파일 (*)",
        )
        if not path:
            return

        self.settings["steamcmd_path"] = path
        save_settings(self.settings)
        self._refresh_steam_tool_status()
        self._log("INFO", f"외부 SteamCMD 경로 저장: {path}")

    def _install_managed_steamcmd(self) -> None:
        if self.steamcmd_service.is_running:
            QMessageBox.information(self, "Steam 도구", "모드 다운로드가 진행 중입니다.")
            return

        self.install_steamcmd_btn.setEnabled(False)
        self.external_steamcmd_btn.setEnabled(False)
        self.steam_status_label.setText("◉ 설치/복구 중...")
        self._log("INFO", "관리형 SteamCMD 설치/복구를 시작합니다.")

        worker = FunctionWorker(
            progress_fn=lambda emit: self.steamcmd_manager.install_or_repair(emit)
        )
        worker.signals.progress.connect(
            lambda text: self._log("INFO", f"[Steam 도구] {text}")
        )
        worker.signals.succeeded.connect(self._on_steamcmd_install_success)
        worker.signals.failed.connect(self._on_steamcmd_install_error)
        self._start_worker(worker)

    @Slot(object)
    def _on_steamcmd_install_success(self, payload: object) -> None:
        self.install_steamcmd_btn.setEnabled(True)
        self.external_steamcmd_btn.setEnabled(True)
        self._refresh_steam_tool_status()
        self._log("INFO", f"관리형 SteamCMD 준비 완료: {payload}")

        if self._pending_download_id:
            pending = self._pending_download_id
            self._pending_download_id = ""
            current = self.mod_list.currentItem()
            if current and str(current.data(Qt.UserRole) or "") == pending:
                self._download_selected_mod()

    @Slot(str)
    def _on_steamcmd_install_error(self, message: str) -> None:
        self.install_steamcmd_btn.setEnabled(True)
        self.external_steamcmd_btn.setEnabled(True)
        self._pending_download_id = ""
        self._refresh_steam_tool_status()
        self._log("ERROR", f"SteamCMD 설치/복구 실패: {message}")
        QMessageBox.warning(self, "SteamCMD 설치 실패", message)

    def _pick_mods(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Mods 폴더 선택")
        if path:
            self.mods_edit.setText(path)

    def _save_settings(self) -> None:
        app_id = self._resolved_app_id()
        if not app_id:
            QMessageBox.warning(self, "설정 저장", "게임/App ID를 먼저 지정해 주세요.")
            return

        games = dict(self.settings.get("games", {}))
        game_cfg = dict(games.get(app_id, {}))
        if self.current_game_name:
            game_cfg["name"] = self.current_game_name
        game_cfg["mods_path"] = self.mods_edit.text().strip()
        games[app_id] = game_cfg

        self.settings["active_game"] = app_id
        self.settings["games"] = games
        self.settings["steamcmd_mode"] = "managed_preferred"
        self.settings["steam_auth_mode"] = self._current_auth_mode()
        self.settings["steam_username"] = self.steam_username_edit.text().strip()
        # Password / Steam Guard values are intentionally never persisted.
        save_settings(self.settings)
        self._log("INFO", "config/user_settings.json 에 설정을 저장했습니다.")

    def _search_game(self) -> None:
        query = self.game_edit.text().strip()
        if not query:
            return

        self.game_search_btn.setEnabled(False)
        self._log("INFO", f"게임 검색 시작: {query}")

        worker = FunctionWorker(fn=lambda: self.app_service.search(query))
        worker.signals.succeeded.connect(self._on_game_results)
        worker.signals.failed.connect(self._on_game_search_error)
        self._start_worker(worker)

    @Slot(object)
    def _on_game_results(self, payload: object) -> None:
        self.game_search_btn.setEnabled(True)
        results = list(payload or [])
        if not results:
            self._log("WARN", "게임 검색 결과가 없습니다.")
            QMessageBox.information(self, "게임 검색", "검색 결과가 없습니다.")
            return

        selected: GameSearchResult
        if len(results) == 1:
            selected = results[0]
        else:
            labels = [f"{item.name}  [{item.app_id}]" for item in results]
            choice, ok = QInputDialog.getItem(
                self,
                "게임 선택",
                "검색 결과",
                labels,
                0,
                False,
            )
            if not ok:
                self._log("INFO", "게임 선택을 취소했습니다.")
                return
            selected = results[labels.index(choice)]

        self._apply_game_selection(selected)

    @Slot(str)
    def _on_game_search_error(self, message: str) -> None:
        self.game_search_btn.setEnabled(True)
        self._log("ERROR", f"게임 검색 실패: {message}")
        QMessageBox.warning(self, "게임 검색 실패", message)

    def _apply_game_selection(self, game: GameSearchResult) -> None:
        previous_app_id = self._resolved_app_id()
        self.game_edit.setText(game.app_id)
        self.current_game_name = game.name
        self.game_name_label.setText(game.name)

        game_cfg = self.settings.get("games", {}).get(game.app_id, {})
        known_mods_path = str(game_cfg.get("mods_path", "") or "")
        if known_mods_path:
            self.mods_edit.setText(known_mods_path)
        elif previous_app_id != game.app_id:
            self.mods_edit.clear()
            self._log(
                "WARN",
                "등록되지 않은 게임입니다. 다운로드 전에 해당 게임의 Mods 경로를 지정해 주세요.",
            )

        self._log("INFO", f"게임 선택: {game.name} / App ID {game.app_id}")

    def _search_mods(self) -> None:
        app_id = self._resolved_app_id()
        if not app_id:
            QMessageBox.warning(
                self,
                "Workshop 검색",
                "게임 이름을 '게임 찾기'로 선택하거나 숫자 App ID를 입력해 주세요.",
            )
            return

        query = self.mod_search_edit.text().strip()
        self.mod_search_btn.setEnabled(False)
        self.mod_list.clear()
        self.detail.clear()
        self.preview_label.setText("검색 중...")
        self.result_count_label.setText("")
        self.open_workshop_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.workshop_items.clear()
        self._thumbnail_generation += 1

        self._log(
            "INFO",
            f"Workshop 검색 시작: app_id={app_id}, query={query or '(인기 항목)'}",
        )

        worker = FunctionWorker(
            fn=lambda: self.workshop_service.search(app_id=app_id, query=query, page=1)
        )
        worker.signals.succeeded.connect(self._on_workshop_results)
        worker.signals.failed.connect(self._on_workshop_search_error)
        self._start_worker(worker)

    @Slot(object)
    def _on_workshop_results(self, payload: object) -> None:
        self.mod_search_btn.setEnabled(True)
        items: list[WorkshopItem] = list(payload or [])
        mods_root = Path(self.mods_edit.text().strip()) if self.mods_edit.text().strip() else None

        self.mod_list.clear()
        self.workshop_items.clear()

        if not items:
            self.preview_label.setText("결과 없음")
            self.result_count_label.setText("0개")
            self._log("WARN", "Workshop 검색 결과가 없습니다.")
            return

        generation = self._thumbnail_generation
        for item in items:
            if mods_root is not None:
                item.installed = (mods_root / item.published_file_id).is_dir()

            self.workshop_items[item.published_file_id] = item
            list_item = QListWidgetItem(self._list_item_text(item))
            list_item.setData(Qt.UserRole, item.published_file_id)
            list_item.setSizeHint(QSize(100, 108))
            self.mod_list.addItem(list_item)

            if item.preview_url:
                self._request_thumbnail(item, list_item, generation)

        self.result_count_label.setText(f"{len(items)}개")
        self.preview_label.setText("항목을 선택하세요")
        self._log("INFO", f"Workshop 검색 완료: {len(items)}개")

        if self.mod_list.count():
            self.mod_list.setCurrentRow(0)

    @Slot(str)
    def _on_workshop_search_error(self, message: str) -> None:
        self.mod_search_btn.setEnabled(True)
        self.preview_label.setText("검색 실패")
        self._log("ERROR", f"Workshop 검색 실패: {message}")
        QMessageBox.warning(self, "Workshop 검색 실패", message)

    def _download_selected_mod(self) -> None:
        if self.steamcmd_service.is_running:
            QMessageBox.information(self, "다운로드", "이미 SteamCMD 다운로드가 진행 중입니다.")
            return

        current = self.mod_list.currentItem()
        if current is None:
            return

        workshop_id = str(current.data(Qt.UserRole) or "")
        item = self.workshop_items.get(workshop_id)
        app_id = self._resolved_app_id()
        mods_path_text = self.mods_edit.text().strip()

        if item is None or not app_id:
            return
        if not mods_path_text:
            QMessageBox.warning(self, "다운로드", "Mods 경로를 먼저 지정해 주세요.")
            return

        mods_root = Path(mods_path_text)
        if not mods_root.exists():
            answer = QMessageBox.question(
                self,
                "Mods 폴더 생성",
                f"Mods 폴더가 없습니다. 생성할까요?\n\n{mods_root}",
            )
            if answer != QMessageBox.Yes:
                return
            try:
                mods_root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, "Mods 폴더", str(exc))
                return

        resolved = self.steamcmd_manager.resolve(
            str(self.settings.get("steamcmd_path", "") or "")
        )
        if resolved is None:
            answer = QMessageBox.question(
                self,
                "SteamCMD 자동 설치",
                "SteamCMD가 준비되어 있지 않습니다.\n"
                "WorkshopPilot 관리 영역에 자동 설치할까요?",
            )
            if answer != QMessageBox.Yes:
                return
            self._pending_download_id = workshop_id
            self._install_managed_steamcmd()
            return

        mode, steamcmd_exe = resolved
        self._active_download_id = workshop_id
        self._active_download_app_id = app_id
        self._active_mods_root = str(mods_root)

        self.download_btn.setEnabled(False)
        self.download_btn.setText("SteamCMD 다운로드 중...")
        self._log(
            "INFO",
            f"모드 다운로드 시작: {item.title} / {workshop_id} / SteamCMD={mode}",
        )

        try:
            auth_mode = self._current_auth_mode()
            username = self.steam_username_edit.text().strip()

            if auth_mode == "account" and not username:
                username, ok = QInputDialog.getText(
                    self,
                    "Steam 계정",
                    "Steam 계정명을 입력해 주세요.",
                )
                username = username.strip()
                if not ok or not username:
                    self.download_btn.setEnabled(True)
                    self.download_btn.setText("선택 모드 다운로드 / 설치")
                    self._log("INFO", "Steam 계정 로그인을 취소했습니다.")
                    return
                self.steam_username_edit.setText(username)

            self._log(
                "INFO",
                f"Steam 인증 방식: {self._auth_mode_label(auth_mode)}",
            )
            self.steamcmd_service.download_workshop_item(
                steamcmd_exe=steamcmd_exe,
                app_id=app_id,
                workshop_id=workshop_id,
                auth_mode=auth_mode,
                username=username,
            )
        except Exception as exc:
            self.download_btn.setEnabled(True)
            self.download_btn.setText("선택 모드 다운로드 / 설치")
            self._log("ERROR", f"SteamCMD 실행 실패: {exc}")
            QMessageBox.warning(self, "SteamCMD 실행 실패", str(exc))

    def _on_auth_mode_changed(self, *_args: object) -> None:
        mode = self._current_auth_mode()
        # In auto mode the username is optional and used only when anonymous fails.
        self.steam_username_edit.setEnabled(mode != "anonymous")
        if mode == "anonymous":
            self.steam_username_edit.setToolTip(
                "익명 모드에서는 Steam 계정명이 사용되지 않습니다."
            )
        elif mode == "auto":
            self.steam_username_edit.setToolTip(
                "비워도 됩니다. 익명 다운로드가 거부될 때 계정명을 물어봅니다."
            )
        else:
            self.steam_username_edit.setToolTip(
                "Steam 계정명만 저장할 수 있습니다. 비밀번호는 저장하지 않습니다."
            )

    def _current_auth_mode(self) -> str:
        value = self.auth_mode_combo.currentData()
        return str(value or "auto")

    @staticmethod
    def _auth_mode_label(mode: str) -> str:
        return {
            "auto": "자동 (익명 우선)",
            "anonymous": "익명",
            "account": "Steam 계정",
        }.get(mode, mode)

    @Slot(str)
    def _on_auth_fallback_required(self, reason: str) -> None:
        self._log("WARN", reason)

        answer = QMessageBox.question(
            self,
            "Steam 계정 인증 필요",
            f"{reason}\n\n"
            "Steam 계정으로 다시 시도할까요?\n"
            "계정명은 저장할 수 있지만 비밀번호와 Steam Guard 코드는 저장하지 않습니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            self.steamcmd_service.fail_pending_auth(
                "익명 다운로드가 거부되었고 Steam 계정 재시도를 취소했습니다."
            )
            return

        username = self.steam_username_edit.text().strip()
        if not username:
            username, ok = QInputDialog.getText(
                self,
                "Steam 계정",
                "Steam 계정명을 입력해 주세요.",
            )
            username = username.strip()
            if not ok or not username:
                self.steamcmd_service.fail_pending_auth(
                    "Steam 계정 로그인을 취소했습니다."
                )
                return
            self.steam_username_edit.setText(username)

        self._log(
            "INFO",
            f"Steam 계정 '{username}'으로 Workshop 다운로드를 재시도합니다.",
        )
        try:
            self.steamcmd_service.retry_with_account(username)
        except Exception as exc:
            self.steamcmd_service.fail_pending_auth(
                f"Steam 계정 재시도 시작 실패: {exc}"
            )

    @Slot(str, str)
    def _on_steam_credential_required(self, kind: str, prompt: str) -> None:
        if kind == "password":
            value, ok = QInputDialog.getText(
                self,
                "Steam 로그인",
                prompt + "\n\n입력값은 저장되지 않습니다.",
                QLineEdit.Password,
            )
        else:
            value, ok = QInputDialog.getText(
                self,
                "Steam Guard",
                prompt + "\n\n입력값은 저장되지 않습니다.",
            )

        if not ok or not value:
            self._log("INFO", f"Steam 인증 입력을 취소했습니다: {kind}")
            self.steamcmd_service.cancel_current(
                "사용자가 Steam 인증 입력을 취소했습니다."
            )
            return

        try:
            self.steamcmd_service.submit_credential(kind, value)
            self._log(
                "INFO",
                "Steam 비밀번호를 전달했습니다. (저장 안 함)"
                if kind == "password"
                else "Steam Guard 코드를 전달했습니다. (저장 안 함)",
            )
        except Exception as exc:
            self._log("ERROR", f"Steam 인증 입력 전달 실패: {exc}")
            self.steamcmd_service.cancel_current(
                f"Steam 인증 입력 전달 실패: {exc}"
            )

    @Slot(bool, str, str)
    def _on_steamcmd_completed(self, success: bool, message: str, source_path: str) -> None:
        if not success:
            self.download_btn.setEnabled(True)
            self.download_btn.setText("선택 모드 다운로드 / 설치")
            self._log("ERROR", message)
            QMessageBox.warning(self, "모드 다운로드 실패", message)
            return

        self._log("INFO", message)
        self.download_btn.setText("Mods 폴더 설치 중...")

        app_id = self._active_download_app_id
        workshop_id = self._active_download_id
        mods_root = Path(self._active_mods_root)
        source = Path(source_path)
        adapter = get_game_adapter(app_id)
        validator = adapter.validate_mod_folder if adapter is not None else None

        worker = FunctionWorker(
            fn=lambda: install_mod_folder(
                source=source,
                mods_root=mods_root,
                destination_name=workshop_id,
                validator=validator,
            )
        )
        worker.signals.succeeded.connect(self._on_mod_install_success)
        worker.signals.failed.connect(self._on_mod_install_error)
        self._start_worker(worker)

    @Slot(object)
    def _on_mod_install_success(self, payload: object) -> None:
        workshop_id = self._active_download_id
        item = self.workshop_items.get(workshop_id)
        if item is not None:
            item.installed = True
            self._refresh_list_item(workshop_id)

        self.download_btn.setEnabled(True)
        self.download_btn.setText("선택 모드 다운로드 / 설치")
        self._log("INFO", f"Mods 폴더 설치 완료: {payload}")

        current = self.mod_list.currentItem()
        if current is not None:
            self._on_mod_selected(current, None)

        QMessageBox.information(
            self,
            "설치 완료",
            f"모드 설치가 완료되었습니다.\n\n{payload}",
        )

    @Slot(str)
    def _on_mod_install_error(self, message: str) -> None:
        self.download_btn.setEnabled(True)
        self.download_btn.setText("선택 모드 다운로드 / 설치")
        self._log("ERROR", f"Mods 폴더 설치 실패: {message}")
        QMessageBox.warning(self, "모드 설치 실패", message)

    def _refresh_list_item(self, workshop_id: str) -> None:
        item = self.workshop_items.get(workshop_id)
        if item is None:
            return
        for row in range(self.mod_list.count()):
            list_item = self.mod_list.item(row)
            if str(list_item.data(Qt.UserRole) or "") == workshop_id:
                list_item.setText(self._list_item_text(item))
                break

    @staticmethod
    def _list_item_text(item: WorkshopItem) -> str:
        status = "[설치됨] " if item.installed else ""
        return f"{status}{item.title}\nWorkshop ID: {item.published_file_id}"

    def _start_worker(self, worker: FunctionWorker) -> None:
        self._active_workers.add(worker)

        def release(*_args: object) -> None:
            self._active_workers.discard(worker)

        worker.signals.succeeded.connect(release)
        worker.signals.failed.connect(release)
        self.thread_pool.start(worker)

    def _request_thumbnail(
        self,
        item: WorkshopItem,
        list_item: QListWidgetItem,
        generation: int,
    ) -> None:
        cached = self.pixmap_cache.get(item.published_file_id)
        if cached is not None:
            list_item.setIcon(QIcon(cached))
            return

        reply = self.network.get(QNetworkRequest(QUrl(item.preview_url)))
        reply.finished.connect(
            lambda r=reply, mod=item, row_item=list_item, gen=generation: (
                self._thumbnail_finished(r, mod, row_item, gen)
            )
        )

    def _thumbnail_finished(
        self,
        reply: QNetworkReply,
        item: WorkshopItem,
        list_item: QListWidgetItem,
        generation: int,
    ) -> None:
        try:
            if generation != self._thumbnail_generation:
                return
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return

            pixmap = QPixmap()
            if not pixmap.loadFromData(reply.readAll()):
                return

            self.pixmap_cache[item.published_file_id] = pixmap
            list_item.setIcon(QIcon(pixmap))

            current = self.mod_list.currentItem()
            if current and current.data(Qt.UserRole) == item.published_file_id:
                self._set_preview_pixmap(pixmap)
        finally:
            reply.deleteLater()

    def _on_mod_selected(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self.detail.clear()
            self.open_workshop_btn.setEnabled(False)
            self.download_btn.setEnabled(False)
            return

        published_id = str(current.data(Qt.UserRole) or "")
        item = self.workshop_items.get(published_id)
        if item is None:
            return

        self.open_workshop_btn.setEnabled(True)
        self.download_btn.setEnabled(not self.steamcmd_service.is_running)

        pixmap = self.pixmap_cache.get(published_id)
        if pixmap is not None:
            self._set_preview_pixmap(pixmap)
        else:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(
                "미리보기 로딩 중..." if item.preview_url else "미리보기 없음"
            )

        updated = self._format_timestamp(item.time_updated)
        created = self._format_timestamp(item.time_created)
        size = self._format_size(item.file_size)
        tags = ", ".join(item.tags) if item.tags else "-"
        installed = "예" if item.installed else "아니오"
        description = self._plain_description(item.description)

        self.detail.setPlainText(
            f"{item.title}\n\n"
            f"Workshop ID: {item.published_file_id}\n"
            f"Creator SteamID: {item.author or '-'}\n"
            f"설치됨: {installed}\n"
            f"생성: {created}\n"
            f"업데이트: {updated}\n"
            f"파일 크기: {size}\n"
            f"구독 수: {item.subscriptions:,}\n"
            f"즐겨찾기 수: {item.favorited:,}\n"
            f"태그: {tags}\n\n"
            f"{description or '(설명 없음)'}"
        )

    def _set_preview_pixmap(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            620,
            260,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)

    def _open_selected_workshop(self) -> None:
        current = self.mod_list.currentItem()
        if current is None:
            return
        published_id = str(current.data(Qt.UserRole) or "")
        item = self.workshop_items.get(published_id)
        if item is not None:
            QDesktopServices.openUrl(QUrl(item.workshop_url))

    def _resolved_app_id(self) -> str:
        value = self.game_edit.text().strip()
        return value if value.isdigit() else ""

    @staticmethod
    def _format_timestamp(value: int) -> str:
        if not value:
            return "-"
        try:
            return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            return str(value)

    @staticmethod
    def _format_size(value: int) -> str:
        if value <= 0:
            return "-"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(value)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{value} B"

    @staticmethod
    def _plain_description(value: str) -> str:
        if not value:
            return ""
        text = re.sub(
            r"\[/?(?:h\d|b|i|u|strike|spoiler|quote|code|list|olist)\]",
            "",
            value,
            flags=re.I,
        )
        text = re.sub(
            r"\[url(?:=[^\]]+)?\](.*?)\[/url\]",
            r"\1",
            text,
            flags=re.I | re.S,
        )
        text = re.sub(r"\[img\].*?\[/img\]", "[이미지]", text, flags=re.I | re.S)
        return text.strip()

    def _log(self, level: str, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{timestamp}] {level}: {text}")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.steamcmd_service.is_running:
            self.steamcmd_service.stop()
        super().closeEvent(event)


def run_app() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    raise SystemExit(app.exec())
