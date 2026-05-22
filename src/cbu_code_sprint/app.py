from __future__ import annotations

import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .locking import SingleInstanceError, SingleInstanceLock
from .paths import AppPaths
from .privacy import mask_name
from .scoring import ScoreInput, calculate_accuracy, calculate_score, count_positional_typos
from .snippets import Snippet, canonical_language, choose_snippet, load_snippets, snippets_for_language
from .storage import Database

LANGUAGES = ["Python", "C", "C++", "Java", "JavaScript", "아직 잘 모름"]
CODE_FONT = QFont("Menlo", 14)


class NoPastePlainTextEdit(QPlainTextEdit):
    backspace_pressed = Signal()
    paste_blocked = Signal()

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_blocked.emit()
            event.ignore()
            return
        if event.key() == Qt.Key.Key_Backspace:
            self.backspace_pressed.emit()
        super().keyPressEvent(event)

    def insertFromMimeData(self, source: Any) -> None:  # noqa: N802 - Qt override name
        self.paste_blocked.emit()
        return

    def contextMenuEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name
        event.ignore()


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths):
        super().__init__()
        self.paths = paths
        self.paths.ensure_directories()
        self.db = Database(paths.database)
        self.db.initialize()
        self.snippets = self._load_snippets()
        self.event_date = date.today().isoformat()

        self.current_name = ""
        self.current_phone = ""
        self.current_main_language = ""
        self.current_snippet: Snippet | None = None
        self.started_at: float | None = None
        self.finished = False
        self.backspace_count = 0
        self.last_score = 0
        self.last_duration_ms = 0
        self.last_accuracy = 0.0
        self.last_typo_count = 0

        self.setWindowTitle("씨부엉 코드 스프린트")
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._update_timer_label)

        self.start_page = self._build_start_page()
        self.game_page = self._build_game_page()
        self.result_page = self._build_result_page()
        self.leaderboard_page = self._build_leaderboard_page()
        self.admin_page = self._build_admin_page()
        for page in [self.start_page, self.game_page, self.result_page, self.leaderboard_page, self.admin_page]:
            self.stack.addWidget(page)

        shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        shortcut.activated.connect(self._request_admin)

        self._apply_style()
        self.resize(1280, 720)

    def _load_snippets(self) -> list[Snippet]:
        try:
            return load_snippets(self.paths.snippets)
        except FileNotFoundError:
            return []

    def _build_start_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(48, 36, 48, 36)
        root.setSpacing(20)

        title = QLabel("씨부엉 코드 스프린트")
        title.setObjectName("Title")
        subtitle = QLabel("이름, 전화번호, 주언어를 입력한 뒤 코드를 빠르고 정확하게 따라 쳐보세요.")
        subtitle.setObjectName("Subtitle")

        top = QHBoxLayout()
        top.addWidget(self._mascot_label("logo_main.png", 180))
        text_box = QVBoxLayout()
        text_box.addWidget(title)
        text_box.addWidget(subtitle)
        text_box.addWidget(QLabel("키보드가 영문 입력 상태인지 확인해주세요."))
        top.addLayout(text_box, stretch=1)
        root.addLayout(top)

        card = QFrame()
        card.setObjectName("Card")
        form = QFormLayout(card)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("예: 홍길동")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("예: 010-1234-5678")
        self.language_input = QComboBox()
        self.language_input.addItems(LANGUAGES)
        form.addRow("이름", self.name_input)
        form.addRow("전화번호", self.phone_input)
        form.addRow("주언어", self.language_input)
        root.addWidget(card)

        actions = QHBoxLayout()
        start_button = QPushButton("시작하기")
        start_button.setObjectName("PrimaryButton")
        start_button.clicked.connect(self._start_game)
        leaderboard_button = QPushButton("리더보드")
        leaderboard_button.clicked.connect(self._show_leaderboard)
        actions.addStretch(1)
        actions.addWidget(leaderboard_button)
        actions.addWidget(start_button)
        root.addLayout(actions)
        root.addStretch(1)
        return page

    def _build_game_page(self) -> QWidget:
        page = QWidget()
        root = QGridLayout(page)
        root.setContentsMargins(32, 24, 32, 24)
        root.setHorizontalSpacing(18)
        root.setVerticalSpacing(12)

        self.game_title = QLabel("준비")
        self.game_title.setObjectName("SectionTitle")
        self.timer_label = QLabel("00.0s")
        self.timer_label.setObjectName("Timer")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setFont(CODE_FONT)
        self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_view.setObjectName("CodeBox")

        self.typing_input = NoPastePlainTextEdit()
        self.typing_input.setFont(CODE_FONT)
        self.typing_input.setObjectName("InputBox")
        self.typing_input.setPlaceholderText("첫 글자를 입력하는 순간 타이머가 시작됩니다.")
        self.typing_input.textChanged.connect(self._on_typing_changed)
        self.typing_input.backspace_pressed.connect(self._on_backspace)
        self.typing_input.paste_blocked.connect(self._show_paste_blocked)

        self.accuracy_label = QLabel("정확도 100.00%")
        self.typo_label = QLabel("오타 0")
        self.backspace_label = QLabel("Backspace 0")

        root.addWidget(self.game_title, 0, 0, 1, 2)
        root.addWidget(self.timer_label, 0, 2)
        root.addWidget(self.code_view, 1, 0, 1, 3)
        root.addWidget(self.typing_input, 2, 0, 1, 3)
        root.addWidget(self.progress, 3, 0, 1, 3)
        root.addWidget(self.accuracy_label, 4, 0)
        root.addWidget(self.typo_label, 4, 1)
        root.addWidget(self.backspace_label, 4, 2)
        return page

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(48, 36, 48, 36)
        root.setSpacing(16)
        root.addWidget(self._mascot_label("mascot_success.png", 130), alignment=Qt.AlignmentFlag.AlignCenter)
        self.result_title = QLabel("결과")
        self.result_title.setObjectName("Title")
        self.result_summary = QLabel("")
        self.result_summary.setObjectName("ResultSummary")
        root.addWidget(self.result_title, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.result_summary, alignment=Qt.AlignmentFlag.AlignCenter)

        actions = QHBoxLayout()
        retry_button = QPushButton("다시 도전")
        retry_button.clicked.connect(self._start_game)
        leaderboard_button = QPushButton("리더보드")
        leaderboard_button.clicked.connect(self._show_leaderboard)
        home_button = QPushButton("처음으로")
        home_button.clicked.connect(lambda: self.stack.setCurrentWidget(self.start_page))
        actions.addStretch(1)
        actions.addWidget(retry_button)
        actions.addWidget(leaderboard_button)
        actions.addWidget(home_button)
        actions.addStretch(1)
        root.addLayout(actions)
        root.addStretch(1)
        return page

    def _build_leaderboard_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(32, 24, 32, 24)
        header = QHBoxLayout()
        title = QLabel("리더보드")
        title.setObjectName("SectionTitle")
        refresh_button = QPushButton("새로고침")
        refresh_button.clicked.connect(self._refresh_leaderboards)
        home_button = QPushButton("처음으로")
        home_button.clicked.connect(lambda: self.stack.setCurrentWidget(self.start_page))
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(refresh_button)
        header.addWidget(home_button)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.all_table = self._make_table()
        self.today_table = self._make_table()
        language_widget = QWidget()
        language_layout = QVBoxLayout(language_widget)
        self.leaderboard_language = QComboBox()
        self.leaderboard_language.addItems(["Python", "C", "C++", "Java", "JavaScript"])
        self.leaderboard_language.currentTextChanged.connect(self._refresh_leaderboards)
        self.language_table = self._make_table()
        language_layout.addWidget(self.leaderboard_language)
        language_layout.addWidget(self.language_table)
        self.tabs.addTab(self.all_table, "전체 TOP 10")
        self.tabs.addTab(self.today_table, "오늘 TOP 10")
        self.tabs.addTab(language_widget, "언어별 TOP 10")
        root.addWidget(self.tabs)
        return page

    def _build_admin_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(14)
        title = QLabel("관리자")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        self.db_path_label = QLabel(str(self.paths.database))
        self.event_date_input = QDateEdit(QDate.currentDate())
        self.event_date_input.setCalendarPopup(True)
        self.event_date_input.dateChanged.connect(self._set_event_date_from_widget)
        form = QFormLayout()
        form.addRow("현재 DB 경로", self.db_path_label)
        form.addRow("행사 날짜", self.event_date_input)
        root.addLayout(form)

        self.stats_label = QLabel("")
        root.addWidget(self.stats_label)

        self.admin_tabs = QTabWidget()
        self.admin_participants_table = self._make_admin_table(
            ["ID", "이름", "전화번호", "주언어", "시도", "최고점", "등록"]
        )
        self.admin_attempts_table = self._make_admin_table(
            ["날짜", "이름", "전화번호", "주언어", "점수", "시간", "정확도", "오타", "Backspace", "문제"]
        )
        self.admin_tabs.addTab(self.admin_participants_table, "참가자 목록")
        self.admin_tabs.addTab(self.admin_attempts_table, "선택 날짜 시도 기록")
        root.addWidget(self.admin_tabs, stretch=1)

        actions = QHBoxLayout()
        backup_button = QPushButton("DB 백업 생성")
        backup_button.clicked.connect(self._backup_database)
        export_public_button = QPushButton("공개 리더보드 CSV")
        export_public_button.clicked.connect(self._export_public_csv)
        export_all_button = QPushButton("전체 데이터 CSV(개인정보 포함)")
        export_all_button.clicked.connect(self._export_all_csv)
        home_button = QPushButton("처음으로")
        home_button.clicked.connect(lambda: self.stack.setCurrentWidget(self.start_page))
        for button in [backup_button, export_public_button, export_all_button, home_button]:
            actions.addWidget(button)
        root.addLayout(actions)

        danger = QFrame()
        danger.setObjectName("DangerCard")
        danger_layout = QVBoxLayout(danger)
        danger_title = QLabel("위험 기능")
        danger_title.setObjectName("DangerTitle")
        danger_layout.addWidget(danger_title)
        danger_buttons = QHBoxLayout()
        delete_date_button = QPushButton("현재 날짜 데이터 삭제")
        delete_date_button.clicked.connect(self._delete_current_date_data)
        reset_button = QPushButton("리더보드 초기화")
        reset_button.clicked.connect(self._reset_leaderboard_data)
        anonymize_button = QPushButton("개인정보 삭제")
        anonymize_button.clicked.connect(self._anonymize_personal_data)
        delete_all_button = QPushButton("전체 데이터 삭제")
        delete_all_button.clicked.connect(self._delete_all_data)
        for button in [delete_date_button, reset_button, anonymize_button, delete_all_button]:
            danger_buttons.addWidget(button)
        danger_layout.addLayout(danger_buttons)
        danger_note = QLabel("각 작업은 실행 전 확인 다이얼로그를 띄우고, 가능한 경우 먼저 DB 백업을 생성합니다.")
        danger_note.setObjectName("Subtitle")
        danger_layout.addWidget(danger_note)
        root.addWidget(danger)
        root.addStretch(1)
        return page

    def _make_table(self) -> QTableWidget:
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["순위", "이름", "언어", "점수", "시간", "정확도", "날짜"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        return table

    def _make_admin_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        return table

    def _start_game(self) -> None:
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()
        language = self.language_input.currentText()
        if not name or not phone:
            QMessageBox.warning(self, "입력 필요", "이름과 전화번호를 입력해주세요.")
            return
        candidates = snippets_for_language(self.snippets, language)
        if not candidates:
            QMessageBox.critical(self, "문제 없음", f"{language} 문제를 찾을 수 없습니다. config/snippets.json을 확인해주세요.")
            return

        self.current_name = name
        self.current_phone = phone
        self.current_main_language = language
        self.current_snippet = choose_snippet(self.snippets, language)
        self.started_at = None
        self.finished = False
        self.backspace_count = 0
        self.last_score = 0
        self.last_duration_ms = 0
        self.last_accuracy = 0.0
        self.last_typo_count = 0

        self.game_title.setText(f"{self.current_snippet.language} · {self.current_snippet.title}")
        self.code_view.setPlainText(self.current_snippet.code)
        self.typing_input.setPlainText("")
        self.typing_input.setEnabled(True)
        self.timer_label.setText("00.0s")
        self.progress.setValue(0)
        self.accuracy_label.setText("정확도 100.00%")
        self.typo_label.setText("오타 0")
        self.backspace_label.setText("Backspace 0")
        self.stack.setCurrentWidget(self.game_page)
        self.typing_input.setFocus()

    def _on_backspace(self) -> None:
        if self.finished:
            return
        self.backspace_count += 1
        self.backspace_label.setText(f"Backspace {self.backspace_count}")

    def _show_paste_blocked(self) -> None:
        self.statusBar().showMessage("붙여넣기는 사용할 수 없습니다.", 2500)

    def _on_typing_changed(self) -> None:
        if self.finished or self.current_snippet is None:
            return
        typed = self.typing_input.toPlainText()
        if typed and self.started_at is None:
            self.started_at = time.monotonic()
            self.timer.start()

        expected = self.current_snippet.code
        typo_count = count_positional_typos(expected, typed)
        accuracy = calculate_accuracy(expected, typed)
        self.last_typo_count = typo_count
        self.last_accuracy = accuracy
        self.typo_label.setText(f"오타 {typo_count}")
        self.accuracy_label.setText(f"정확도 {accuracy:.2f}%")
        progress = 0 if not expected else min(100, int((len(typed) / len(expected)) * 100))
        self.progress.setValue(progress)
        if typed == expected:
            self._finish_attempt()

    def _finish_attempt(self) -> None:
        if self.current_snippet is None:
            return
        self.finished = True
        self.timer.stop()
        self.typing_input.setEnabled(False)
        now = time.monotonic()
        started = self.started_at or now
        duration_ms = max(0, int((now - started) * 1000))
        expected = self.current_snippet.code
        typed = self.typing_input.toPlainText()
        accuracy = calculate_accuracy(expected, typed)
        typo_count = count_positional_typos(expected, typed)
        score = calculate_score(
            ScoreInput(
                duration_ms=duration_ms,
                accuracy=accuracy,
                typo_count=typo_count,
                backspace_count=self.backspace_count,
            )
        )
        self.db.record_attempt(
            name=self.current_name,
            phone=self.current_phone,
            main_language=self.current_main_language,
            event_date=self.event_date,
            language=self.current_snippet.language,
            snippet_id=self.current_snippet.id,
            duration_ms=duration_ms,
            accuracy=accuracy,
            typo_count=typo_count,
            backspace_count=self.backspace_count,
            score=score,
        )
        self.last_score = score
        self.last_duration_ms = duration_ms
        self.last_accuracy = accuracy
        self.last_typo_count = typo_count
        display_name = mask_name(self.current_name)
        self.result_summary.setText(
            f"{display_name} · {self.current_snippet.language}\n"
            f"점수 {score}점 · 시간 {duration_ms / 1000:.2f}s · 정확도 {accuracy:.2f}%\n"
            f"오타 {typo_count} · Backspace {self.backspace_count}"
        )
        self.stack.setCurrentWidget(self.result_page)

    def _update_timer_label(self) -> None:
        if self.started_at is None:
            self.timer_label.setText("00.0s")
            return
        elapsed = time.monotonic() - self.started_at
        self.timer_label.setText(f"{elapsed:04.1f}s")

    def _show_leaderboard(self) -> None:
        current_language = canonical_language(self.language_input.currentText())
        if current_language in ["Python", "C", "C++", "Java", "JavaScript"]:
            self.leaderboard_language.setCurrentText(current_language)
        self._refresh_leaderboards()
        self.stack.setCurrentWidget(self.leaderboard_page)

    def _refresh_leaderboards(self) -> None:
        self._populate_table(self.all_table, self.db.public_leaderboard(limit=10))
        self._populate_table(self.today_table, self.db.public_leaderboard(limit=10, event_date=self.event_date))
        self._populate_table(
            self.language_table,
            self.db.public_leaderboard(limit=10, language=self.leaderboard_language.currentText()),
        )

    def _populate_table(self, table: QTableWidget, rows: list[dict[str, Any]]) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["rank"],
                row["display_name"],
                row["language"],
                row["score"],
                f"{row['duration_seconds']:.2f}s",
                f"{row['accuracy']:.2f}%",
                row["event_date_label"],
            ]
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _request_admin(self) -> None:
        password, ok = QInputDialog.getText(self, "관리자", "비밀번호", QLineEdit.EchoMode.Password)
        expected = os.environ.get("CBU_CODE_SPRINT_ADMIN_PASSWORD", "cbu")
        if not ok:
            return
        if password != expected:
            QMessageBox.warning(self, "실패", "관리자 비밀번호가 맞지 않습니다.")
            return
        self._show_admin()

    def _show_admin(self) -> None:
        self._refresh_admin_stats()
        self.stack.setCurrentWidget(self.admin_page)

    def _set_event_date_from_widget(self, value: QDate) -> None:
        self.event_date = value.toString("yyyy-MM-dd")
        self._refresh_admin_stats()

    def _refresh_admin_stats(self) -> None:
        stats = self.db.stats(event_date=self.event_date)
        self.stats_label.setText(
            f"전체 참가자 {stats['participants_total']}명 · 오늘 참가자 {stats['participants_today']}명\n"
            f"전체 시도 {stats['attempts_total']}회 · 오늘 시도 {stats['attempts_today']}회"
        )
        self._populate_admin_participants()
        self._populate_admin_attempts()

    def _populate_admin_participants(self) -> None:
        rows = self.db.participants()
        self.admin_participants_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["id"],
                row["name"],
                row["phone"],
                row["main_language"],
                row["attempt_count"],
                row["best_score"] if row["best_score"] is not None else "-",
                row["created_at"],
            ]
            for column, value in enumerate(values):
                self.admin_participants_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _populate_admin_attempts(self) -> None:
        rows = self.db.attempts(event_date=self.event_date)
        self.admin_attempts_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["event_date"],
                row["name"],
                row["phone"],
                row["main_language"],
                row["score"],
                f"{int(row['duration_ms']) / 1000:.2f}s",
                f"{float(row['accuracy']):.2f}%",
                row["typo_count"],
                row["backspace_count"],
                row["snippet_id"],
            ]
            for column, value in enumerate(values):
                self.admin_attempts_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _backup_database(self) -> None:
        path = self.db.backup(self.paths.backups_dir)
        QMessageBox.information(self, "백업 완료", f"DB 백업을 생성했습니다.\n{path}")
        self._refresh_admin_stats()

    def _export_public_csv(self) -> None:
        path = self.db.export_public_leaderboard_csv(self.paths.exports_dir, event_date=self.event_date)
        QMessageBox.information(self, "CSV 생성 완료", f"공개 리더보드 CSV를 생성했습니다.\n{path}")

    def _export_all_csv(self) -> None:
        path = self.db.export_all_attempts_csv(self.paths.exports_dir, event_date=self.event_date)
        QMessageBox.information(self, "CSV 생성 완료", f"개인정보 포함 CSV를 생성했습니다.\n{path}")

    def _confirm_danger(self, title: str, message: str) -> bool:
        result = QMessageBox.warning(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def _backup_before_danger(self) -> Path:
        return self.db.backup(self.paths.backups_dir)

    def _delete_current_date_data(self) -> None:
        if not self._confirm_danger(
            "현재 날짜 데이터 삭제",
            f"{self.event_date} 날짜의 시도 기록을 삭제합니다.\n"
            "다른 날짜 기록은 유지되지만, 해당 날짜만 참가한 참가자는 함께 정리됩니다.\n계속할까요?",
        ):
            return
        backup_path = self._backup_before_danger()
        result = self.db.delete_attempts_for_date(self.event_date)
        self._refresh_admin_stats()
        QMessageBox.information(
            self,
            "삭제 완료",
            f"백업: {backup_path}\n"
            f"삭제된 시도: {result['attempts_deleted']}개\n"
            f"정리된 참가자: {result['orphan_participants_deleted']}명",
        )

    def _reset_leaderboard_data(self) -> None:
        if not self._confirm_danger(
            "리더보드 초기화",
            "모든 시도 기록을 삭제해서 리더보드를 비웁니다.\n참가자 연락처 기록은 유지됩니다.\n계속할까요?",
        ):
            return
        backup_path = self._backup_before_danger()
        result = self.db.reset_leaderboard()
        self._refresh_admin_stats()
        QMessageBox.information(
            self,
            "초기화 완료",
            f"백업: {backup_path}\n삭제된 시도: {result['attempts_deleted']}개",
        )

    def _anonymize_personal_data(self) -> None:
        if not self._confirm_danger(
            "개인정보 삭제",
            "참가자 이름과 전화번호를 삭제합니다.\n시도 기록과 점수는 익명 상태로 유지됩니다.\n계속할까요?",
        ):
            return
        backup_path = self._backup_before_danger()
        result = self.db.anonymize_personal_data()
        self._refresh_admin_stats()
        QMessageBox.information(
            self,
            "개인정보 삭제 완료",
            f"백업: {backup_path}\n익명 처리된 참가자: {result['participants_anonymized']}명",
        )

    def _delete_all_data(self) -> None:
        if not self._confirm_danger(
            "전체 데이터 삭제",
            "모든 참가자와 모든 시도 기록을 삭제합니다.\n이 작업은 되돌릴 수 없으므로 백업 파일을 확인해주세요.\n계속할까요?",
        ):
            return
        backup_path = self._backup_before_danger()
        result = self.db.delete_all_data()
        self._refresh_admin_stats()
        QMessageBox.information(
            self,
            "전체 삭제 완료",
            f"백업: {backup_path}\n"
            f"삭제된 시도: {result['attempts_deleted']}개\n"
            f"삭제된 참가자: {result['participants_deleted']}명",
        )

    def _mascot_label(self, filename: str, size: int) -> QLabel:
        label = QLabel("🦉 CBU")
        label.setObjectName("Mascot")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = self.paths.assets_dir / "mascot" / filename
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                label.setPixmap(
                    pixmap.scaled(
                        size,
                        size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        return label

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #0B1020; color: #E5E7EB; font-size: 16px; }
            QLabel#Title { font-size: 42px; font-weight: 800; color: #FACC15; }
            QLabel#SectionTitle { font-size: 30px; font-weight: 800; color: #FACC15; }
            QLabel#Subtitle { color: #94A3B8; }
            QLabel#DangerTitle { font-size: 20px; font-weight: 800; color: #F87171; }
            QLabel#Timer { font-size: 28px; font-weight: 800; color: #34D399; }
            QLabel#ResultSummary { font-size: 24px; line-height: 150%; }
            QLabel#Mascot { font-size: 42px; color: #FACC15; }
            QFrame#Card, QFrame#DangerCard { background: #121A2E; border: 1px solid #1F2A44; border-radius: 16px; padding: 22px; }
            QFrame#DangerCard { border-color: #7F1D1D; }
            QLineEdit, QComboBox, QPlainTextEdit, QDateEdit {
                background: #050816; color: #E5E7EB; border: 1px solid #334155;
                border-radius: 10px; padding: 10px;
            }
            QPlainTextEdit#CodeBox { color: #CBD5E1; }
            QPlainTextEdit#InputBox { color: #FACC15; }
            QPushButton {
                background: #1E293B; color: #E5E7EB; border: 1px solid #334155;
                border-radius: 10px; padding: 10px 18px; font-weight: 700;
            }
            QPushButton:hover { background: #334155; }
            QPushButton#PrimaryButton { background: #FACC15; color: #0B1020; }
            QProgressBar { background: #050816; border: 1px solid #334155; border-radius: 8px; text-align: center; }
            QProgressBar::chunk { background: #34D399; border-radius: 8px; }
            QTabWidget::pane { border: 1px solid #334155; }
            QHeaderView::section { background: #121A2E; color: #FACC15; padding: 8px; border: 0; }
            QTableWidget { background: #050816; gridline-color: #1F2A44; }
            """
        )


def run_app(*, home: str | Path, fullscreen: bool = False) -> int:
    qt_app = QApplication.instance() or QApplication(sys.argv)
    paths = AppPaths.from_home(home)
    paths.ensure_directories()
    try:
        with SingleInstanceLock(paths.lock_file):
            window = MainWindow(paths)
            if fullscreen:
                window.showFullScreen()
            else:
                window.show()
            return int(qt_app.exec())
    except SingleInstanceError:
        QMessageBox.critical(
            None,
            "이미 실행 중",
            "씨부엉 코드 스프린트가 이미 실행 중입니다.\n"
            "USB 데이터 보호를 위해 한 번에 한 인스턴스만 실행할 수 있습니다.",
        )
        return 3
