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

from app.core.settings import load_settings, save_settings
from app.core.steam_app_service import SteamAppService
from app.core.workshop_service import WorkshopService
from app.models.game import GameSearchResult
from app.models.workshop_item import WorkshopItem


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class FunctionWorker(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.succeeded.emit(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WorkshopPilot")
        self.resize(1320, 820)

        self.settings = load_settings()
        self.app_service = SteamAppService()
        self.workshop_service = WorkshopService()
        self.thread_pool = QThreadPool.globalInstance()
        self.network = QNetworkAccessManager(self)

        self.current_game_name = ""
        self.workshop_items: dict[str, WorkshopItem] = {}
        self.pixmap_cache: dict[str, QPixmap] = {}
        self._thumbnail_generation = 0
        self._active_workers: set[FunctionWorker] = set()

        self._build_ui()
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
        self.download_btn = QPushButton("선택 모드 다운로드 (다음 단계)")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(
            lambda: self._log("INFO", "다운로드 기능은 다음 패치에서 QProcess로 연결합니다.")
        )
        button_row.addWidget(self.open_workshop_btn)
        button_row.addWidget(self.download_btn, 1)
        right_layout.addLayout(button_row)

        splitter.addWidget(right)
        splitter.setSizes([520, 780])
        layout.addWidget(splitter, 1)

        layout.addWidget(QLabel("로그"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMaximumHeight(170)
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
        self.current_game_name = str(game_cfg.get("name", ""))
        self.game_name_label.setText(self.current_game_name)
        self.mods_edit.setText(game_cfg.get("mods_path", r"C:\games\RimWorld\Mods"))
        self._log("INFO", "초기 설정을 불러왔습니다.")

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

        self.settings["steamcmd_path"] = self.steamcmd_edit.text().strip()
        self.settings["active_game"] = app_id
        self.settings["games"] = games
        save_settings(self.settings)
        self._log("INFO", "config/user_settings.json 에 설정을 저장했습니다.")

    def _search_game(self) -> None:
        query = self.game_edit.text().strip()
        if not query:
            return

        self.game_search_btn.setEnabled(False)
        self._log("INFO", f"게임 검색 시작: {query}")

        worker = FunctionWorker(lambda: self.app_service.search(query))
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
        self.game_edit.setText(game.app_id)
        self.current_game_name = game.name
        self.game_name_label.setText(game.name)

        game_cfg = self.settings.get("games", {}).get(game.app_id, {})
        known_mods_path = str(game_cfg.get("mods_path", "") or "")
        if known_mods_path:
            self.mods_edit.setText(known_mods_path)

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
            lambda: self.workshop_service.search(app_id=app_id, query=query, page=1)
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
            status = "[설치됨] " if item.installed else ""
            list_item = QListWidgetItem(
                f"{status}{item.title}\nWorkshop ID: {item.published_file_id}"
            )
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
        self.download_btn.setEnabled(True)

        pixmap = self.pixmap_cache.get(published_id)
        if pixmap is not None:
            self._set_preview_pixmap(pixmap)
        else:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("미리보기 로딩 중..." if item.preview_url else "미리보기 없음")

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
        text = re.sub(r"\[/?(?:h\d|b|i|u|strike|spoiler|quote|code|list|olist)\]", "", value, flags=re.I)
        text = re.sub(r"\[url(?:=[^\]]+)?\](.*?)\[/url\]", r"\1", text, flags=re.I | re.S)
        text = re.sub(r"\[img\].*?\[/img\]", "[이미지]", text, flags=re.I | re.S)
        return text.strip()

    def _log(self, level: str, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{timestamp}] {level}: {text}")


def run_app() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    raise SystemExit(app.exec())
