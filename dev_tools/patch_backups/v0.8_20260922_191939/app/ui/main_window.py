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
    QAbstractItemView,
    QFileDialog,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.install_metadata_service import InstallMetadataService
from app.core.installed_mod_service import InstalledModService
from app.core.installer import install_mod_folder
from app.core.settings import load_settings, save_settings
from app.core.steam_app_service import SteamAppService
from app.core.steamcmd_manager import SteamCmdManager
from app.core.steamcmd_service import SteamCmdService
from app.core.workshop_service import WorkshopService
from app.games.registry import get_game_adapter
from app.models.download_task import DownloadTask
from app.models.installed_mod import InstalledMod
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
        self.install_metadata_service = InstallMetadataService()
        self.installed_mod_service = InstalledModService(
            metadata=self.install_metadata_service
        )
        self.steamcmd_manager = SteamCmdManager()
        self.steamcmd_service = SteamCmdService(self)
        self.thread_pool = QThreadPool.globalInstance()
        self.network = QNetworkAccessManager(self)

        self.current_game_name = ""
        self.workshop_items: dict[str, WorkshopItem] = {}
        self.installed_mods: dict[str, InstalledMod] = {}
        self.pixmap_cache: dict[str, QPixmap] = {}
        self._thumbnail_generation = 0
        self._active_workers: set[FunctionWorker] = set()
        self._pending_download_id = ""  # legacy single-download compatibility
        self._pending_batch_context: dict[str, object] | None = None

        self.download_tasks: dict[str, DownloadTask] = {}
        self.download_queue_order: list[str] = []
        self.queue_rows: dict[str, QTreeWidgetItem] = {}
        self._queue_running = False
        self._queue_cancel_requested = False
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

        self.main_tabs = QTabWidget()
        self.main_tabs.currentChanged.connect(self._on_main_tab_changed)
        layout.addWidget(self.main_tabs, 1)

        # -------------------------------------------------------------
        # Workshop 탐색 탭
        # -------------------------------------------------------------
        browse_tab = QWidget()
        browse_layout = QVBoxLayout(browse_tab)

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
        browse_layout.addLayout(search_row)

        selection_row = QHBoxLayout()
        self.checked_count_label = QLabel("체크 0개")
        self.check_all_btn = QPushButton("전체 체크")
        self.check_all_btn.clicked.connect(self._check_all_results)
        self.clear_checks_btn = QPushButton("체크 해제")
        self.clear_checks_btn.clicked.connect(self._clear_result_checks)
        self.batch_download_btn = QPushButton("체크 모드 다운로드 / 설치")
        self.batch_download_btn.setEnabled(False)
        self.batch_download_btn.clicked.connect(self._download_checked_mods)

        selection_row.addWidget(self.checked_count_label)
        selection_row.addWidget(self.check_all_btn)
        selection_row.addWidget(self.clear_checks_btn)
        selection_row.addStretch(1)
        selection_row.addWidget(self.batch_download_btn)
        browse_layout.addLayout(selection_row)

        splitter = QSplitter(Qt.Horizontal)

        self.mod_list = QListWidget()
        self.mod_list.setIconSize(QSize(96, 96))
        self.mod_list.setSpacing(3)
        self.mod_list.currentItemChanged.connect(self._on_mod_selected)
        self.mod_list.itemChanged.connect(self._on_result_item_changed)
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
        browse_layout.addWidget(splitter, 1)

        queue_title_row = QHBoxLayout()
        queue_title_row.addWidget(QLabel("다운로드 큐"))
        self.queue_summary_label = QLabel("대기열 없음")
        queue_title_row.addWidget(self.queue_summary_label)
        queue_title_row.addStretch(1)

        self.retry_failed_btn = QPushButton("실패 항목 재시도")
        self.retry_failed_btn.setEnabled(False)
        self.retry_failed_btn.clicked.connect(self._retry_failed_tasks)
        self.cancel_queue_btn = QPushButton("큐 중지")
        self.cancel_queue_btn.setEnabled(False)
        self.cancel_queue_btn.clicked.connect(self._cancel_download_queue)
        self.clear_queue_btn = QPushButton("완료/실패 기록 지우기")
        self.clear_queue_btn.clicked.connect(self._clear_download_queue)

        queue_title_row.addWidget(self.retry_failed_btn)
        queue_title_row.addWidget(self.cancel_queue_btn)
        queue_title_row.addWidget(self.clear_queue_btn)
        browse_layout.addLayout(queue_title_row)

        self.queue_tree = QTreeWidget()
        self.queue_tree.setHeaderLabels(["상태", "모드", "Workshop ID", "메시지"])
        self.queue_tree.setRootIsDecorated(False)
        self.queue_tree.setAlternatingRowColors(True)
        self.queue_tree.setMaximumHeight(155)
        self.queue_tree.setColumnWidth(0, 110)
        self.queue_tree.setColumnWidth(1, 330)
        self.queue_tree.setColumnWidth(2, 130)
        browse_layout.addWidget(self.queue_tree)

        self.queue_progress = QProgressBar()
        self.queue_progress.setRange(0, 1)
        self.queue_progress.setValue(0)
        self.queue_progress.setFormat("대기열 없음")
        browse_layout.addWidget(self.queue_progress)

        self.main_tabs.addTab(browse_tab, "Workshop 탐색")

        # -------------------------------------------------------------
        # 설치된 모드 관리 탭
        # -------------------------------------------------------------
        installed_tab = QWidget()
        installed_layout = QVBoxLayout(installed_tab)

        installed_toolbar = QHBoxLayout()
        self.installed_count_label = QLabel("설치된 모드: 확인 전")
        self.installed_refresh_btn = QPushButton("새로고침")
        self.installed_refresh_btn.clicked.connect(self._scan_installed_mods)

        self.installed_check_updates_btn = QPushButton("업데이트 확인")
        self.installed_check_updates_btn.clicked.connect(
            self._check_installed_mod_updates
        )
        self.installed_update_available_btn = QPushButton("업데이트 있는 모드만 설치")
        self.installed_update_available_btn.setEnabled(False)
        self.installed_update_available_btn.clicked.connect(
            self._update_available_installed_mods
        )

        self.installed_open_folder_btn = QPushButton("폴더 열기")
        self.installed_open_folder_btn.clicked.connect(self._open_installed_mod_folder)
        self.installed_open_workshop_btn = QPushButton("Workshop 열기")
        self.installed_open_workshop_btn.clicked.connect(
            self._open_installed_mod_workshop
        )
        self.installed_reinstall_btn = QPushButton("선택 재설치 / 업데이트")
        self.installed_reinstall_btn.clicked.connect(
            self._reinstall_selected_installed_mods
        )
        self.installed_update_all_btn = QPushButton("Workshop 모드 전체 업데이트")
        self.installed_update_all_btn.clicked.connect(
            self._update_all_installed_workshop_mods
        )
        self.installed_delete_btn = QPushButton("선택 삭제")
        self.installed_delete_btn.clicked.connect(self._delete_selected_installed_mods)

        installed_toolbar.addWidget(self.installed_count_label)
        installed_toolbar.addStretch(1)
        installed_toolbar.addWidget(self.installed_refresh_btn)
        installed_toolbar.addWidget(self.installed_check_updates_btn)
        installed_toolbar.addWidget(self.installed_update_available_btn)
        installed_toolbar.addWidget(self.installed_open_folder_btn)
        installed_toolbar.addWidget(self.installed_open_workshop_btn)
        installed_toolbar.addWidget(self.installed_reinstall_btn)
        installed_toolbar.addWidget(self.installed_update_all_btn)
        installed_toolbar.addWidget(self.installed_delete_btn)
        installed_layout.addLayout(installed_toolbar)

        self.installed_tree = QTreeWidget()
        self.installed_tree.setHeaderLabels(
            [
                "상태",
                "업데이트",
                "모드 이름",
                "Workshop ID",
                "Package ID",
                "지원 버전",
                "폴더",
            ]
        )
        self.installed_tree.setRootIsDecorated(False)
        self.installed_tree.setAlternatingRowColors(True)
        self.installed_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.installed_tree.itemSelectionChanged.connect(
            self._on_installed_selection_changed
        )
        self.installed_tree.setColumnWidth(0, 100)
        self.installed_tree.setColumnWidth(1, 120)
        self.installed_tree.setColumnWidth(2, 280)
        self.installed_tree.setColumnWidth(3, 130)
        self.installed_tree.setColumnWidth(4, 230)
        self.installed_tree.setColumnWidth(5, 150)
        installed_layout.addWidget(self.installed_tree, 1)

        self.installed_detail = QPlainTextEdit()
        self.installed_detail.setReadOnly(True)
        self.installed_detail.setMaximumHeight(135)
        self.installed_detail.setPlaceholderText(
            "설치된 모드를 선택하면 로컬 메타데이터가 표시됩니다."
        )
        installed_layout.addWidget(self.installed_detail)

        self.main_tabs.addTab(installed_tab, "설치된 모드 관리")

        # 공통 로그 / 설정
        layout.addWidget(QLabel("로그"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setMaximumHeight(175)
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

        if self._pending_batch_context is not None:
            context = self._pending_batch_context
            self._pending_batch_context = None
            self._enqueue_batch_context(context)
        elif self._pending_download_id:
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
        self._pending_batch_context = None
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
        self.checked_count_label.setText("체크 0개")
        self.batch_download_btn.setEnabled(False)
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
            list_item.setFlags(
                list_item.flags()
                | Qt.ItemIsUserCheckable
                | Qt.ItemIsSelectable
                | Qt.ItemIsEnabled
            )
            list_item.setCheckState(Qt.Unchecked)
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
        current = self.mod_list.currentItem()
        if current is None:
            return
        workshop_id = str(current.data(Qt.UserRole) or "")
        if workshop_id:
            self._start_download_requests([workshop_id])

    def _download_checked_mods(self) -> None:
        workshop_ids = self._checked_workshop_ids()
        if not workshop_ids:
            QMessageBox.information(
                self,
                "다운로드",
                "체크된 Workshop 모드가 없습니다.",
            )
            return
        self._start_download_requests(workshop_ids)

    def _start_download_requests(self, workshop_ids: list[str]) -> None:
        app_id = self._resolved_app_id()
        mods_path_text = self.mods_edit.text().strip()

        if not app_id:
            QMessageBox.warning(self, "다운로드", "게임/App ID를 먼저 지정해 주세요.")
            return
        if not mods_path_text:
            QMessageBox.warning(self, "다운로드", "Mods 경로를 먼저 지정해 주세요.")
            return

        valid_items: list[WorkshopItem] = []
        seen: set[str] = set()
        for workshop_id in workshop_ids:
            if workshop_id in seen:
                continue
            seen.add(workshop_id)
            item = self.workshop_items.get(workshop_id)
            if item is not None:
                valid_items.append(item)

        if not valid_items:
            QMessageBox.warning(self, "다운로드", "다운로드할 유효한 모드가 없습니다.")
            return

        mods_root = Path(mods_path_text)
        if not mods_root.exists():
            answer = QMessageBox.question(
                self,
                "Mods 폴더 생성",
                f"Mods 폴더가 없습니다. 생성할까요?\\n\\n{mods_root}",
            )
            if answer != QMessageBox.Yes:
                return
            try:
                mods_root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, "Mods 폴더", str(exc))
                return

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
                self._log("INFO", "Steam 계정 로그인을 취소했습니다.")
                return
            self.steam_username_edit.setText(username)

        context: dict[str, object] = {
            "app_id": app_id,
            "mods_root": str(mods_root),
            "auth_mode": auth_mode,
            "username": username,
            "items": [
                (
                    item.published_file_id,
                    item.title,
                    item.time_updated,
                )
                for item in valid_items
            ],
        }

        resolved = self.steamcmd_manager.resolve(
            str(self.settings.get("steamcmd_path", "") or "")
        )
        if resolved is None:
            answer = QMessageBox.question(
                self,
                "SteamCMD 자동 설치",
                "SteamCMD가 준비되어 있지 않습니다.\\n"
                "WorkshopPilot 관리 영역에 자동 설치할까요?",
            )
            if answer != QMessageBox.Yes:
                return
            self._pending_batch_context = context
            self._install_managed_steamcmd()
            return

        self._enqueue_batch_context(context)

    def _enqueue_batch_context(self, context: dict[str, object]) -> None:
        app_id = str(context.get("app_id", "") or "")
        mods_root = str(context.get("mods_root", "") or "")
        auth_mode = str(context.get("auth_mode", "auto") or "auto")
        username = str(context.get("username", "") or "")
        items = list(context.get("items", []) or [])

        added = 0
        reset = 0
        for raw in items:
            if len(raw) >= 3:
                workshop_id, title, remote_time_updated = raw[:3]
            else:
                workshop_id, title = raw[:2]
                remote_time_updated = 0

            workshop_id = str(workshop_id)
            title = str(title)
            try:
                remote_time_updated = int(remote_time_updated or 0)
            except (TypeError, ValueError):
                remote_time_updated = 0

            task = self.download_tasks.get(workshop_id)
            if task is None:
                task = DownloadTask(
                    workshop_id=workshop_id,
                    title=title,
                    app_id=app_id,
                    mods_root=mods_root,
                    auth_mode=auth_mode,
                    username=username,
                    remote_time_updated=remote_time_updated,
                )
                self.download_tasks[workshop_id] = task
                self.download_queue_order.append(workshop_id)

                row = QTreeWidgetItem(
                    ["대기", task.title, task.workshop_id, ""]
                )
                row.setData(0, Qt.UserRole, workshop_id)
                self.queue_tree.addTopLevelItem(row)
                self.queue_rows[workshop_id] = row
                added += 1
            elif task.status not in {"downloading", "installing"}:
                task.title = title
                task.app_id = app_id
                task.mods_root = mods_root
                task.auth_mode = auth_mode
                task.username = username
                task.remote_time_updated = remote_time_updated
                task.status = "queued"
                task.message = ""
                reset += 1
                self._refresh_queue_row(task)

        self._queue_cancel_requested = False
        self._log(
            "INFO",
            f"다운로드 큐 등록: 신규 {added}개 / 다시 대기 {reset}개 / "
            f"총 {len(self.download_tasks)}개",
        )
        self._update_queue_summary()
        self._start_next_queue_task()

    def _start_next_queue_task(self) -> None:
        if self._active_download_id:
            return

        if self._queue_cancel_requested:
            self._finish_queue()
            return

        next_task: DownloadTask | None = None
        for workshop_id in self.download_queue_order:
            task = self.download_tasks.get(workshop_id)
            if task is not None and task.status == "queued":
                next_task = task
                break

        if next_task is None:
            self._finish_queue()
            return

        resolved = self.steamcmd_manager.resolve(
            str(self.settings.get("steamcmd_path", "") or "")
        )
        if resolved is None:
            next_task.status = "failed"
            next_task.message = "SteamCMD를 찾을 수 없습니다."
            self._refresh_queue_row(next_task)
            self._log("ERROR", next_task.message)
            self._start_next_queue_task()
            return

        mode, steamcmd_exe = resolved

        self._queue_running = True
        self._active_download_id = next_task.workshop_id
        self._active_download_app_id = next_task.app_id
        self._active_mods_root = next_task.mods_root
        next_task.status = "downloading"
        next_task.message = f"SteamCMD={mode}"
        next_task.attempts += 1
        self._refresh_queue_row(next_task)
        self._set_queue_controls_running(True)
        self._update_queue_summary()

        self._log(
            "INFO",
            f"[큐] 다운로드 시작: {next_task.title} / "
            f"{next_task.workshop_id} / {next_task.attempts}회차",
        )
        self._log(
            "INFO",
            f"Steam 인증 방식: {self._auth_mode_label(next_task.auth_mode)}",
        )

        try:
            self.steamcmd_service.download_workshop_item(
                steamcmd_exe=steamcmd_exe,
                app_id=next_task.app_id,
                workshop_id=next_task.workshop_id,
                auth_mode=next_task.auth_mode,
                username=next_task.username,
            )
        except Exception as exc:
            next_task.status = "failed"
            next_task.message = f"SteamCMD 실행 실패: {exc}"
            self._refresh_queue_row(next_task)
            self._log("ERROR", next_task.message)
            self._active_download_id = ""
            self._start_next_queue_task()

    def _finish_queue(self) -> None:
        was_running = self._queue_running
        self._queue_running = False
        self._active_download_id = ""
        self._active_download_app_id = ""
        self._active_mods_root = ""
        self._set_queue_controls_running(False)
        self._update_queue_summary()

        if not was_running:
            return

        completed = sum(
            1 for task in self.download_tasks.values()
            if task.status == "completed"
        )
        failed = sum(
            1 for task in self.download_tasks.values()
            if task.status == "failed"
        )
        cancelled = sum(
            1 for task in self.download_tasks.values()
            if task.status == "cancelled"
        )

        self._log(
            "INFO",
            f"다운로드 큐 종료: 완료 {completed} / 실패 {failed} / 취소 {cancelled}",
        )

        if failed:
            QMessageBox.warning(
                self,
                "다운로드 큐 완료",
                f"완료 {completed}개 / 실패 {failed}개 / 취소 {cancelled}개\\n\\n"
                "실패 항목은 '실패 항목 재시도'로 다시 실행할 수 있습니다.",
            )
        else:
            QMessageBox.information(
                self,
                "다운로드 큐 완료",
                f"완료 {completed}개 / 취소 {cancelled}개",
            )

    def _retry_failed_tasks(self) -> None:
        count = 0
        for task in self.download_tasks.values():
            if task.status == "failed":
                task.status = "queued"
                task.message = ""
                self._refresh_queue_row(task)
                count += 1

        if not count:
            return

        self._queue_cancel_requested = False
        self._log("INFO", f"실패 항목 재시도: {count}개")
        self._update_queue_summary()
        self._start_next_queue_task()

    def _cancel_download_queue(self) -> None:
        if not self._queue_running:
            return

        self._queue_cancel_requested = True
        for task in self.download_tasks.values():
            if task.status == "queued":
                task.status = "cancelled"
                task.message = "사용자 취소"
                self._refresh_queue_row(task)

        active = self.download_tasks.get(self._active_download_id)
        if active is not None and active.status == "downloading":
            active.status = "cancelled"
            active.message = "사용자 취소"
            self._refresh_queue_row(active)
            self.steamcmd_service.cancel_current("사용자가 다운로드 큐를 중지했습니다.")
        elif active is None:
            self._finish_queue()
        else:
            self._log(
                "INFO",
                "현재 Mods 폴더 설치 작업이 끝난 뒤 큐를 중지합니다.",
            )

        self._update_queue_summary()

    def _clear_download_queue(self) -> None:
        if self._queue_running:
            QMessageBox.information(
                self,
                "다운로드 큐",
                "큐가 실행 중일 때는 기록을 지울 수 없습니다.",
            )
            return

        self.download_tasks.clear()
        self.download_queue_order.clear()
        self.queue_rows.clear()
        self.queue_tree.clear()
        self._queue_cancel_requested = False
        self._update_queue_summary()

    def _check_all_results(self) -> None:
        self.mod_list.blockSignals(True)
        try:
            for row in range(self.mod_list.count()):
                self.mod_list.item(row).setCheckState(Qt.Checked)
        finally:
            self.mod_list.blockSignals(False)
        self._update_checked_count()

    def _clear_result_checks(self) -> None:
        self.mod_list.blockSignals(True)
        try:
            for row in range(self.mod_list.count()):
                self.mod_list.item(row).setCheckState(Qt.Unchecked)
        finally:
            self.mod_list.blockSignals(False)
        self._update_checked_count()

    def _checked_workshop_ids(self) -> list[str]:
        result: list[str] = []
        for row in range(self.mod_list.count()):
            list_item = self.mod_list.item(row)
            if list_item.checkState() == Qt.Checked:
                workshop_id = str(list_item.data(Qt.UserRole) or "")
                if workshop_id:
                    result.append(workshop_id)
        return result

    @Slot(QListWidgetItem)
    def _on_result_item_changed(self, _item: QListWidgetItem) -> None:
        self._update_checked_count()

    def _update_checked_count(self) -> None:
        count = len(self._checked_workshop_ids())
        self.checked_count_label.setText(f"체크 {count}개")
        self.batch_download_btn.setEnabled(count > 0)

    def _refresh_queue_row(self, task: DownloadTask) -> None:
        row = self.queue_rows.get(task.workshop_id)
        if row is None:
            return

        status_text = {
            "queued": "대기",
            "downloading": "다운로드 중",
            "installing": "설치 중",
            "completed": "완료",
            "failed": "실패",
            "cancelled": "취소",
        }.get(task.status, task.status)

        row.setText(0, status_text)
        row.setText(1, task.title)
        row.setText(2, task.workshop_id)
        row.setText(3, task.message)

    def _update_queue_summary(self) -> None:
        tasks = list(self.download_tasks.values())
        total = len(tasks)

        completed = sum(task.status == "completed" for task in tasks)
        failed = sum(task.status == "failed" for task in tasks)
        cancelled = sum(task.status == "cancelled" for task in tasks)
        queued = sum(task.status == "queued" for task in tasks)
        working = sum(
            task.status in {"downloading", "installing"}
            for task in tasks
        )

        finished = completed + failed + cancelled
        self.queue_progress.setRange(0, max(1, total))
        self.queue_progress.setValue(finished)
        if total:
            self.queue_progress.setFormat(
                f"{finished}/{total} 완료 처리 "
                f"(성공 {completed} / 실패 {failed} / 취소 {cancelled})"
            )
            self.queue_summary_label.setText(
                f"총 {total} / 대기 {queued} / 작업 {working} / "
                f"완료 {completed} / 실패 {failed}"
            )
        else:
            self.queue_progress.setFormat("대기열 없음")
            self.queue_summary_label.setText("대기열 없음")

        self.retry_failed_btn.setEnabled(
            failed > 0 and not self._queue_running
        )

    def _set_queue_controls_running(self, running: bool) -> None:
        self.cancel_queue_btn.setEnabled(running)
        self.retry_failed_btn.setEnabled(
            (not running)
            and any(
                task.status == "failed"
                for task in self.download_tasks.values()
            )
        )
        self.clear_queue_btn.setEnabled(not running)
        self.download_btn.setEnabled(
            (not running) and self.mod_list.currentItem() is not None
        )
        self.batch_download_btn.setEnabled(
            (not running) and bool(self._checked_workshop_ids())
        )
        if hasattr(self, "installed_tree"):
            self._update_installed_action_buttons()

    @Slot(int)
    def _on_main_tab_changed(self, index: int) -> None:
        if self.main_tabs.tabText(index) == "설치된 모드 관리":
            self._scan_installed_mods()

    def _scan_installed_mods(self) -> None:
        mods_text = self.mods_edit.text().strip()
        app_id = self._resolved_app_id()

        if not mods_text:
            self.installed_tree.clear()
            self.installed_mods.clear()
            self.installed_count_label.setText("설치된 모드: Mods 경로 없음")
            return

        mods_root = Path(mods_text)
        self.installed_refresh_btn.setEnabled(False)
        self.installed_count_label.setText("설치된 모드: 검색 중...")

        worker = FunctionWorker(
            fn=lambda: self.installed_mod_service.scan(mods_root, app_id)
        )
        worker.signals.succeeded.connect(self._on_installed_scan_success)
        worker.signals.failed.connect(self._on_installed_scan_error)
        self._start_worker(worker)

    @Slot(object)
    def _on_installed_scan_success(self, payload: object) -> None:
        mods = list(payload) if isinstance(payload, list) else []
        self.installed_mods.clear()

        for mod in mods:
            if isinstance(mod, InstalledMod):
                self.installed_mods[str(mod.path)] = mod

        self.installed_refresh_btn.setEnabled(True)
        self._render_installed_mods()
        self._log(
            "INFO",
            f"설치된 모드 스캔 완료: {len(self.installed_mods)}개",
        )

    def _render_installed_mods(self) -> None:
        self.installed_tree.clear()

        workshop_count = 0
        invalid_count = 0
        update_count = 0
        baseline_missing = 0

        for mod in sorted(
            self.installed_mods.values(),
            key=lambda value: (
                not bool(value.workshop_id),
                value.name.lower(),
                value.folder_name.lower(),
            ),
        ):
            if mod.workshop_id:
                workshop_count += 1
            if not mod.valid:
                invalid_count += 1
            if mod.needs_update:
                update_count += 1
            if mod.update_status == "baseline_missing":
                baseline_missing += 1

            status = "정상" if mod.valid else "경고"
            if mod.workshop_id:
                status += " / Workshop"

            row = QTreeWidgetItem(
                [
                    status,
                    mod.update_status_text,
                    mod.name,
                    mod.workshop_id or "-",
                    mod.package_id or "-",
                    mod.versions_text,
                    mod.folder_name,
                ]
            )
            row.setData(0, Qt.UserRole, str(mod.path))
            if not mod.valid:
                row.setToolTip(0, mod.message)
                row.setToolTip(2, mod.message)

            if mod.update_status == "update_available":
                row.setToolTip(
                    1,
                    "Steam Workshop에 설치 기준보다 새로운 업데이트가 있습니다.",
                )
            elif mod.update_status == "baseline_missing":
                row.setToolTip(
                    1,
                    "이 모드는 v0.7 이전에 설치되어 정확한 설치 기준 시각이 없습니다. "
                    "한 번 재설치/업데이트하면 이후부터 정확히 비교할 수 있습니다.",
                )

            self.installed_tree.addTopLevelItem(row)

        self.installed_count_label.setText(
            f"설치된 모드: {len(self.installed_mods)}개 / "
            f"Workshop {workshop_count}개 / "
            f"업데이트 {update_count}개 / "
            f"기준 없음 {baseline_missing}개 / "
            f"경고 {invalid_count}개"
        )
        self._update_installed_action_buttons()

    @Slot(str)
    def _on_installed_scan_error(self, message: str) -> None:
        self.installed_refresh_btn.setEnabled(True)
        self.installed_count_label.setText("설치된 모드: 스캔 실패")
        self._log("ERROR", f"설치된 모드 스캔 실패: {message}")

    def _selected_installed_mods(self) -> list[InstalledMod]:
        result: list[InstalledMod] = []
        for row in self.installed_tree.selectedItems():
            key = str(row.data(0, Qt.UserRole) or "")
            mod = self.installed_mods.get(key)
            if mod is not None:
                result.append(mod)
        return result

    def _on_installed_selection_changed(self) -> None:
        selected = self._selected_installed_mods()
        self._update_installed_action_buttons()

        if len(selected) != 1:
            if not selected:
                self.installed_detail.clear()
            else:
                self.installed_detail.setPlainText(
                    f"{len(selected)}개 모드를 선택했습니다."
                )
            return

        mod = selected[0]
        detail_lines = [
            mod.name,
            "",
            f"폴더: {mod.path}",
            f"Workshop ID: {mod.workshop_id or '-'}",
            f"Package ID: {mod.package_id or '-'}",
            f"저작자: {mod.author or '-'}",
            f"지원 버전: {mod.versions_text}",
            f"업데이트 상태: {mod.update_status_text}",
            f"설치 기준 Workshop 시각: {self._format_unix_time(mod.installed_remote_time_updated)}",
            f"현재 Workshop 시각: {self._format_unix_time(mod.remote_time_updated)}",
            f"로컬 검증: {'정상' if mod.valid else '경고'}",
            f"메시지: {mod.message or '-'}",
        ]
        self.installed_detail.setPlainText("\n".join(detail_lines))

    def _update_installed_action_buttons(self) -> None:
        selected = self._selected_installed_mods()
        one = len(selected) == 1
        has_workshop = bool(selected) and all(mod.workshop_id for mod in selected)

        self.installed_open_folder_btn.setEnabled(one)
        self.installed_open_workshop_btn.setEnabled(
            one and bool(selected[0].workshop_id)
        )
        self.installed_reinstall_btn.setEnabled(
            has_workshop and not self._queue_running
        )
        self.installed_delete_btn.setEnabled(
            bool(selected) and not self._queue_running
        )

        any_workshop = any(
            mod.workshop_id for mod in self.installed_mods.values()
        )
        self.installed_update_all_btn.setEnabled(
            any_workshop and not self._queue_running
        )
        self.installed_check_updates_btn.setEnabled(
            any_workshop and not self._queue_running
        )
        self.installed_update_available_btn.setEnabled(
            (not self._queue_running)
            and any(mod.needs_update for mod in self.installed_mods.values())
        )

    def _check_installed_mod_updates(self) -> None:
        workshop_ids = [
            mod.workshop_id
            for mod in self.installed_mods.values()
            if mod.workshop_id
        ]
        if not workshop_ids:
            return

        self.installed_check_updates_btn.setEnabled(False)
        self.installed_count_label.setText(
            f"설치된 모드: Workshop 업데이트 확인 중... ({len(workshop_ids)}개)"
        )
        self._log(
            "INFO",
            f"설치된 Workshop 모드 업데이트 확인 시작: {len(workshop_ids)}개",
        )

        worker = FunctionWorker(
            fn=lambda: self.workshop_service.get_details(workshop_ids)
        )
        worker.signals.succeeded.connect(self._on_update_check_success)
        worker.signals.failed.connect(self._on_update_check_error)
        self._start_worker(worker)

    @Slot(object)
    def _on_update_check_success(self, payload: object) -> None:
        details = list(payload) if isinstance(payload, list) else []
        by_id = {
            item.published_file_id: item
            for item in details
            if isinstance(item, WorkshopItem)
        }

        update_count = 0
        unavailable_count = 0
        baseline_missing = 0

        for mod in self.installed_mods.values():
            if not mod.workshop_id:
                mod.update_status = "local"
                continue

            remote = by_id.get(mod.workshop_id)
            if remote is None:
                mod.remote_time_updated = 0
                mod.update_status = "unavailable"
                unavailable_count += 1
                continue

            mod.remote_time_updated = int(remote.time_updated or 0)

            if mod.installed_remote_time_updated <= 0:
                mod.update_status = "baseline_missing"
                baseline_missing += 1
            elif (
                mod.remote_time_updated > mod.installed_remote_time_updated
            ):
                mod.update_status = "update_available"
                update_count += 1
            else:
                mod.update_status = "latest"

        self.installed_check_updates_btn.setEnabled(True)
        self._render_installed_mods()
        self._log(
            "INFO",
            f"업데이트 확인 완료: 업데이트 {update_count} / "
            f"기준 없음 {baseline_missing} / 확인 불가 {unavailable_count}",
        )

    @Slot(str)
    def _on_update_check_error(self, message: str) -> None:
        self.installed_check_updates_btn.setEnabled(True)
        self._render_installed_mods()
        self._log("ERROR", f"설치된 모드 업데이트 확인 실패: {message}")
        QMessageBox.warning(self, "업데이트 확인 실패", message)

    def _update_available_installed_mods(self) -> None:
        mods = [
            mod
            for mod in self.installed_mods.values()
            if mod.workshop_id and mod.needs_update
        ]
        if not mods:
            QMessageBox.information(
                self,
                "업데이트",
                "현재 '업데이트 있음'으로 확인된 모드가 없습니다.",
            )
            return

        self._enqueue_installed_mod_updates(mods)

    @staticmethod
    def _format_unix_time(value: int) -> str:
        try:
            value = int(value or 0)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            return "-"
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")

    def _open_installed_mod_folder(self) -> None:
        selected = self._selected_installed_mods()
        if len(selected) != 1:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(selected[0].path)))

    def _open_installed_mod_workshop(self) -> None:
        selected = self._selected_installed_mods()
        if len(selected) != 1 or not selected[0].workshop_url:
            return
        QDesktopServices.openUrl(QUrl(selected[0].workshop_url))

    def _reinstall_selected_installed_mods(self) -> None:
        selected = [
            mod for mod in self._selected_installed_mods()
            if mod.workshop_id
        ]
        if not selected:
            QMessageBox.information(
                self,
                "설치된 모드",
                "Workshop ID가 확인되는 모드를 선택해 주세요.",
            )
            return
        self._enqueue_installed_mod_updates(selected)

    def _update_all_installed_workshop_mods(self) -> None:
        mods = [
            mod for mod in self.installed_mods.values()
            if mod.workshop_id
        ]
        if not mods:
            QMessageBox.information(
                self,
                "전체 업데이트",
                "Workshop ID를 가진 설치 모드가 없습니다.",
            )
            return

        answer = QMessageBox.question(
            self,
            "설치된 Workshop 모드 전체 업데이트",
            f"{len(mods)}개 Workshop 모드를 SteamCMD로 다시 내려받아 "
            "최신 파일로 교체할까요?",
        )
        if answer != QMessageBox.Yes:
            return

        self._enqueue_installed_mod_updates(mods)

    def _enqueue_installed_mod_updates(
        self,
        mods: list[InstalledMod],
    ) -> None:
        app_id = self._resolved_app_id()
        mods_root = self.mods_edit.text().strip()
        if not app_id or not mods_root:
            QMessageBox.warning(
                self,
                "모드 업데이트",
                "App ID와 Mods 경로를 먼저 확인해 주세요.",
            )
            return

        context: dict[str, object] = {
            "app_id": app_id,
            "mods_root": mods_root,
            "auth_mode": self._current_auth_mode(),
            "username": self.steam_username_edit.text().strip(),
            "items": [
                (
                    mod.workshop_id,
                    mod.name,
                    mod.remote_time_updated,
                )
                for mod in mods
                if mod.workshop_id
            ],
        }

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
            self._pending_batch_context = context
            self._install_managed_steamcmd()
            return

        self.main_tabs.setCurrentIndex(0)
        self._enqueue_batch_context(context)

    def _delete_selected_installed_mods(self) -> None:
        selected = self._selected_installed_mods()
        if not selected:
            return

        names = "\n".join(
            f"- {mod.name} ({mod.folder_name})"
            for mod in selected[:12]
        )
        if len(selected) > 12:
            names += f"\n... 외 {len(selected) - 12}개"

        answer = QMessageBox.warning(
            self,
            "설치된 모드 삭제",
            f"다음 {len(selected)}개 모드 폴더를 실제로 삭제합니다.\n\n"
            f"{names}\n\n"
            "계속할까요?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        mods_root = Path(self.mods_edit.text().strip())
        app_id = self._resolved_app_id()
        selected_copy = list(selected)

        def delete_many() -> list[str]:
            deleted: list[str] = []
            for mod in selected_copy:
                self.installed_mod_service.delete(mods_root, mod.path)
                if mod.workshop_id:
                    self.install_metadata_service.remove(
                        app_id,
                        mods_root,
                        mod.workshop_id,
                    )
                deleted.append(str(mod.path))
            return deleted

        self.installed_delete_btn.setEnabled(False)
        worker = FunctionWorker(fn=delete_many)
        worker.signals.succeeded.connect(self._on_installed_delete_success)
        worker.signals.failed.connect(self._on_installed_delete_error)
        self._start_worker(worker)

    @Slot(object)
    def _on_installed_delete_success(self, payload: object) -> None:
        deleted = list(payload) if isinstance(payload, list) else []
        self._log("INFO", f"설치된 모드 삭제 완료: {len(deleted)}개")
        self._scan_installed_mods()

        # 검색 결과의 설치됨 상태도 즉시 다시 계산.
        mods_root = Path(self.mods_edit.text().strip())
        for workshop_id, item in self.workshop_items.items():
            item.installed = (mods_root / workshop_id).is_dir()
            self._refresh_list_item(workshop_id)

    @Slot(str)
    def _on_installed_delete_error(self, message: str) -> None:
        self._log("ERROR", f"설치된 모드 삭제 실패: {message}")
        QMessageBox.warning(self, "모드 삭제 실패", message)
        self._scan_installed_mods()

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
    def _on_steamcmd_completed(
        self,
        success: bool,
        message: str,
        source_path: str,
    ) -> None:
        workshop_id = self._active_download_id
        task = self.download_tasks.get(workshop_id)

        if task is None:
            self._log(
                "ERROR",
                f"활성 다운로드 큐 항목을 찾지 못했습니다: {workshop_id}",
            )
            self._active_download_id = ""
            self._start_next_queue_task()
            return

        if self._queue_cancel_requested and task.status == "cancelled":
            self._log("INFO", f"[큐] 다운로드 취소: {task.title}")
            self._active_download_id = ""
            self._finish_queue()
            return

        if not success:
            task.status = "failed"
            task.message = message
            self._refresh_queue_row(task)
            self._log(
                "ERROR",
                f"[큐] 다운로드 실패: {task.title} / {message}",
            )
            self._active_download_id = ""
            self._update_queue_summary()
            self._start_next_queue_task()
            return

        self._log("INFO", message)
        task.status = "installing"
        task.message = "Mods 폴더에 설치 중..."
        self._refresh_queue_row(task)
        self._update_queue_summary()

        source = Path(source_path)
        mods_root = Path(task.mods_root)
        adapter = get_game_adapter(task.app_id)
        validator = adapter.validate_mod_folder if adapter is not None else None

        worker = FunctionWorker(
            fn=lambda: self._install_task_and_record_metadata(
                task=task,
                source=source,
                mods_root=mods_root,
                validator=validator,
            )
        )
        worker.signals.succeeded.connect(self._on_mod_install_success)
        worker.signals.failed.connect(self._on_mod_install_error)
        self._start_worker(worker)

    @Slot(object)
    def _install_task_and_record_metadata(
        self,
        task: DownloadTask,
        source: Path,
        mods_root: Path,
        validator: object,
    ) -> Path:
        destination = install_mod_folder(
            source=source,
            mods_root=mods_root,
            destination_name=task.workshop_id,
            validator=validator,
        )

        remote_time_updated = int(task.remote_time_updated or 0)
        if remote_time_updated <= 0:
            try:
                details = self.workshop_service.get_details([task.workshop_id])
                if details:
                    remote_time_updated = int(details[0].time_updated or 0)
            except Exception:
                # The install itself succeeded. Update tracking can be refreshed later.
                remote_time_updated = 0

        self.install_metadata_service.record_install(
            task.app_id,
            mods_root,
            task.workshop_id,
            title=task.title,
            remote_time_updated=remote_time_updated,
            destination=destination,
        )
        return destination

    @Slot(object)
    def _on_mod_install_success(self, payload: object) -> None:
        workshop_id = self._active_download_id
        task = self.download_tasks.get(workshop_id)

        if task is not None:
            task.status = "completed"
            task.message = str(payload)
            self._refresh_queue_row(task)

        item = self.workshop_items.get(workshop_id)
        if item is not None:
            item.installed = True
            self._refresh_list_item(workshop_id)

        self._log(
            "INFO",
            f"[큐] Mods 폴더 설치 완료: "
            f"{task.title if task else workshop_id} / {payload}",
        )

        current = self.mod_list.currentItem()
        if current is not None:
            self._on_mod_selected(current, None)

        self._active_download_id = ""
        self._active_download_app_id = ""
        self._active_mods_root = ""
        self._update_queue_summary()

        if hasattr(self, "installed_tree"):
            self._scan_installed_mods()

        if self._queue_cancel_requested:
            self._finish_queue()
        else:
            self._start_next_queue_task()

    @Slot(str)
    def _on_mod_install_error(self, message: str) -> None:
        workshop_id = self._active_download_id
        task = self.download_tasks.get(workshop_id)

        if task is not None:
            task.status = "failed"
            task.message = message
            self._refresh_queue_row(task)

        self._log(
            "ERROR",
            f"[큐] Mods 폴더 설치 실패: "
            f"{task.title if task else workshop_id} / {message}",
        )

        self._active_download_id = ""
        self._active_download_app_id = ""
        self._active_mods_root = ""
        self._update_queue_summary()

        if self._queue_cancel_requested:
            self._finish_queue()
        else:
            self._start_next_queue_task()

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
        self.download_btn.setEnabled(
            not self.steamcmd_service.is_running and not self._queue_running
        )

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
