from __future__ import annotations

import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPixmap,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
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
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .editor import (
    INDENT_UNIT,
    is_submission_complete,
    normalize_newlines,
    submission_text_for_comparison,
    indentation_for_newline,
)
from .locking import SingleInstanceError, SingleInstanceLock
from .paths import AppPaths
from .privacy import mask_name
from .scoring import ScoreInput, calculate_accuracy, calculate_score, count_positional_typos
from .snippets import Snippet, canonical_language, choose_snippet, load_snippets, snippets_for_language
from .storage import Database

LANGUAGES = ["Python", "C", "C++", "Java", "JavaScript", "아직 잘 모름"]
APP_TITLE = "씨부엉 코드 스프린트"
UI_FONT = QFont("Malgun Gothic", 10)
UI_FONT.setStyleHint(QFont.StyleHint.SansSerif)
CODE_FONT = QFont("Cascadia Mono", 14)
CODE_FONT.setStyleHint(QFont.StyleHint.Monospace)


class NoPastePlainTextEdit(QPlainTextEdit):
    backspace_pressed = Signal()
    paste_blocked = Signal()
    submit_requested = Signal()

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_blocked.emit()
            event.ignore()
            return
        if event.key() == Qt.Key.Key_Tab:
            self.insertPlainText(INDENT_UNIT)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Backtab:
            self._unindent_current_line()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.submit_requested.emit()
            else:
                self._insert_newline_with_indent()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Backspace:
            self.backspace_pressed.emit()
        super().keyPressEvent(event)

    def _insert_newline_with_indent(self) -> None:
        cursor = self.textCursor()
        indent = indentation_for_newline(self.toPlainText(), cursor.position())
        cursor.insertText("\n" + indent)
        self.setTextCursor(cursor)

    def _unindent_current_line(self) -> None:
        cursor = self.textCursor()
        position = cursor.position()
        text = self.toPlainText()
        line_start = text.rfind("\n", 0, position) + 1
        removable = 0
        for index in range(min(len(INDENT_UNIT), max(0, len(text) - line_start))):
            if text[line_start + index] != " ":
                break
            removable += 1
        if removable == 0 and line_start < len(text) and text[line_start] == "\t":
            removable = 1
        if removable == 0:
            return
        cursor.setPosition(line_start)
        cursor.setPosition(line_start + removable, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.setPosition(max(line_start, position - removable))
        self.setTextCursor(cursor)

    def insertFromMimeData(self, source: Any) -> None:  # noqa: N802 - Qt override name
        self.paste_blocked.emit()
        return

    def contextMenuEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name
        event.ignore()


class CodeHighlighter(QSyntaxHighlighter):
    """Small dependency-free highlighter for the short challenge snippets."""

    KEYWORDS = {
        "Python": {
            "def",
            "for",
            "in",
            "if",
            "else",
            "elif",
            "return",
            "print",
            "range",
            "sum",
            "True",
            "False",
        },
        "C": {"#include", "int", "void", "return", "for", "if", "else", "printf"},
        "C++": {"#include", "int", "void", "return", "for", "if", "else", "std", "cout"},
        "Java": {"public", "class", "static", "void", "int", "return", "if", "else", "System", "out"},
        "JavaScript": {"const", "let", "function", "return", "if", "else", "for", "console", "log"},
    }

    STRING_PATTERN = re.compile(r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)")
    COMMENT_PATTERN = re.compile(r"(#.*$|//.*$)")
    NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")

    def __init__(self, document: Any):
        super().__init__(document)
        self.language = "Python"
        self.keyword_format = _text_format("#FACC15", bold=True)
        self.string_format = _text_format("#86EFAC")
        self.comment_format = _text_format("#64748B", italic=True)
        self.number_format = _text_format("#93C5FD")

    def set_language(self, language: str) -> None:
        self.language = canonical_language(language)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt override name
        for keyword in self.KEYWORDS.get(self.language, set()):
            pattern = rf"(?<![\w#]){re.escape(keyword)}(?!\w)"
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)
        for match in self.NUMBER_PATTERN.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)
        for match in self.STRING_PATTERN.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)
        for match in self.COMMENT_PATTERN.finditer(text):
            self.setFormat(match.start(), len(text) - match.start(), self.comment_format)


def _text_format(color: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    text_format = QTextCharFormat()
    text_format.setForeground(QColor(color))
    if bold:
        text_format.setFontWeight(QFont.Weight.Bold)
    if italic:
        text_format.setFontItalic(True)
    return text_format


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths):
        super().__init__()
        self.paths = paths
        self.paths.ensure_directories()
        self.db = Database(paths.database)
        self.db.initialize()
        self._pixmap_cache: dict[tuple[str, int], QPixmap] = {}
        self.snippet_load_error = ""
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

        self.setWindowTitle(APP_TITLE)
        self.setFont(UI_FONT)
        app_icon = self.paths.assets_dir / "mascot" / "app_icon.png"
        if app_icon.exists():
            self.setWindowIcon(QIcon(str(app_icon)))
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
        self.statusBar().setObjectName("StatusBar")
        self.statusBar().showMessage("준비 완료", 1800)
        self.resize(1280, 720)

    def _load_snippets(self) -> list[Snippet]:
        try:
            return load_snippets(self.paths.snippets)
        except FileNotFoundError:
            self.snippet_load_error = f"문제 파일을 찾을 수 없습니다: {self.paths.snippets}"
            return []
        except (KeyError, TypeError, ValueError) as exc:
            self.snippet_load_error = f"문제 파일 형식 오류: {exc}"
            return []

    def _card(self, object_name: str = "Card") -> QFrame:
        card = QFrame()
        card.setObjectName(object_name)
        return card

    def _chip(self, text: str, object_name: str = "Chip") -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _metric(self, title: str, value: str, object_name: str = "MetricValue") -> QFrame:
        card = self._card("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("MetricTitle")
        value_label = QLabel(value)
        value_label.setObjectName(object_name)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        card.value_label = value_label  # type: ignore[attr-defined]
        return card

    def _set_metric(self, card: QFrame, value: str) -> None:
        value_label = getattr(card, "value_label", None)
        if isinstance(value_label, QLabel):
            value_label.setText(value)

    def _build_start_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(44, 32, 44, 32)
        root.setSpacing(22)

        header = QHBoxLayout()
        header.setSpacing(18)
        header.addWidget(self._mascot_label("logo_main.png", 104))
        title_box = QVBoxLayout()
        title_box.setSpacing(6)
        title = QLabel(APP_TITLE)
        title.setObjectName("Title")
        subtitle = QLabel("홍보전 현장에서 바로 플레이하는 코드 타자 스프린트")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, stretch=1)
        header.addWidget(self._chip("영문 입력 확인", "AccentChip"))
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(22)

        hero = self._card("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_layout.setSpacing(14)
        hero_layout.addWidget(self._mascot_label("mascot_idle.png", 210), alignment=Qt.AlignmentFlag.AlignCenter)
        hero_title = QLabel("오늘의 스프린트")
        hero_title.setObjectName("SectionTitle")
        hero_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_copy = QLabel("정확히 입력하고, 빠르게 완주하고, 리더보드에 이름을 올리세요.")
        hero_copy.setObjectName("Subtitle")
        hero_copy.setWordWrap(True)
        hero_copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chips = QHBoxLayout()
        chips.setSpacing(10)
        chips.addWidget(self._chip("실시간 정확도"))
        chips.addWidget(self._chip("자동 채점"))
        chips.addWidget(self._chip("공개 순위"))
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_copy)
        hero_layout.addLayout(chips)
        hero_layout.addStretch(1)
        body.addWidget(hero, stretch=5)

        card = self._card()
        form_root = QVBoxLayout(card)
        form_root.setContentsMargins(28, 24, 28, 24)
        form_root.setSpacing(18)
        form_title = QLabel("참가자 등록")
        form_title.setObjectName("SectionTitleSmall")
        form_root.addWidget(form_title)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("예: 홍길동")
        self.name_input.setMaxLength(24)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("예: 010-1234-5678")
        self.phone_input.setMaxLength(24)
        self.language_input = QComboBox()
        self.language_input.addItems(LANGUAGES)
        form.addRow("이름", self.name_input)
        form.addRow("전화번호", self.phone_input)
        form.addRow("주언어", self.language_input)
        form_root.addLayout(form)
        self.start_notice_label = QLabel(self.snippet_load_error or f"문제 {len(self.snippets)}개 준비 완료")
        self.start_notice_label.setObjectName("Notice")
        self.start_notice_label.setWordWrap(True)
        form_root.addWidget(self.start_notice_label)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        start_button = QPushButton("시작하기")
        start_button.setObjectName("PrimaryButton")
        start_button.setMinimumHeight(48)
        start_button.clicked.connect(self._start_game)
        leaderboard_button = QPushButton("리더보드")
        leaderboard_button.setMinimumHeight(48)
        leaderboard_button.clicked.connect(self._show_leaderboard)
        actions.addWidget(leaderboard_button)
        actions.addWidget(start_button)
        form_root.addLayout(actions)
        body.addWidget(card, stretch=4)

        root.addLayout(body, stretch=1)
        root.addStretch(1)
        return page

    def _build_game_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(14)

        self.game_title = QLabel("준비")
        self.game_title.setObjectName("SectionTitle")
        self.game_subtitle = QLabel("첫 글자를 입력하면 타이머가 시작됩니다.")
        self.game_subtitle.setObjectName("Subtitle")
        self.timer_label = QLabel("00.0s")
        self.timer_label.setObjectName("Timer")
        self.game_mascot = self._mascot_label("mascot_guide.png", 82)

        header = QHBoxLayout()
        header.setSpacing(16)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        title_stack.addWidget(self.game_title)
        title_stack.addWidget(self.game_subtitle)
        header.addLayout(title_stack, stretch=1)
        header.addWidget(self.timer_label)
        header.addWidget(self.game_mascot)
        root.addLayout(header)

        arena = QHBoxLayout()
        arena.setSpacing(16)

        editor_column = QVBoxLayout()
        editor_column.setSpacing(12)
        code_label = QLabel("목표 코드")
        code_label.setObjectName("PanelTitle")
        input_label = QLabel("입력")
        input_label.setObjectName("PanelTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")

        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setFont(CODE_FONT)
        self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_view.setObjectName("CodeBox")
        self.code_view.setMinimumHeight(220)
        self.code_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.code_highlighter = CodeHighlighter(self.code_view.document())

        self.typing_input = NoPastePlainTextEdit()
        self.typing_input.setFont(CODE_FONT)
        self.typing_input.setObjectName("InputBox")
        self.typing_input.setTabChangesFocus(False)
        self.typing_input.setMinimumHeight(180)
        self.typing_input.setPlaceholderText(
            "첫 글자를 입력하는 순간 타이머가 시작됩니다. Tab은 4칸, Ctrl+Enter는 제출입니다."
        )
        self.typing_input.textChanged.connect(self._on_typing_changed)
        self.typing_input.backspace_pressed.connect(self._on_backspace)
        self.typing_input.paste_blocked.connect(self._show_paste_blocked)
        self.typing_input.submit_requested.connect(self._submit_attempt)

        self.submit_button = QPushButton("제출하기 (Ctrl+Enter)")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.clicked.connect(self._submit_attempt)
        self.submit_shortcuts = []
        for sequence in ["Ctrl+Return", "Ctrl+Enter"]:
            shortcut = QShortcut(QKeySequence(sequence), self.typing_input)
            shortcut.activated.connect(self._submit_attempt)
            self.submit_shortcuts.append(shortcut)

        self.accuracy_label = QLabel("정확도 100.00%")
        self.accuracy_label.setObjectName("LiveMetric")
        self.typo_label = QLabel("오타 0")
        self.typo_label.setObjectName("LiveMetric")
        self.backspace_label = QLabel("Backspace 0")
        self.backspace_label.setObjectName("LiveMetric")
        self.remaining_label = QLabel("남은 글자 0")
        self.remaining_label.setObjectName("LiveMetric")
        self.live_hint_label = QLabel("키보드가 영문 입력 상태인지 확인해주세요.")
        self.live_hint_label.setObjectName("Notice")
        self.live_hint_label.setWordWrap(True)

        editor_column.addWidget(code_label)
        editor_column.addWidget(self.code_view, stretch=4)
        editor_column.addWidget(input_label)
        editor_column.addWidget(self.typing_input, stretch=3)
        editor_column.addWidget(self.progress)
        arena.addLayout(editor_column, stretch=7)

        side = self._card("SidePanel")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(18, 18, 18, 18)
        side_layout.setSpacing(12)
        side_title = QLabel("라이브 기록")
        side_title.setObjectName("SectionTitleSmall")
        self.player_label = QLabel("참가자 -")
        self.player_label.setObjectName("Subtitle")
        self.snippet_label = QLabel("문제 -")
        self.snippet_label.setObjectName("Subtitle")
        side_layout.addWidget(side_title)
        side_layout.addWidget(self.player_label)
        side_layout.addWidget(self.snippet_label)
        side_layout.addSpacing(6)
        side_layout.addWidget(self.accuracy_label)
        side_layout.addWidget(self.typo_label)
        side_layout.addWidget(self.backspace_label)
        side_layout.addWidget(self.remaining_label)
        side_layout.addWidget(self.live_hint_label)
        side_layout.addStretch(1)
        self.submit_button.setMinimumHeight(46)
        side_layout.addWidget(self.submit_button)
        arena.addWidget(side, stretch=3)

        root.addLayout(arena, stretch=1)
        return page

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(44, 30, 44, 30)
        root.setSpacing(18)

        top = QHBoxLayout()
        top.setSpacing(20)
        self.result_mascot = self._mascot_label("mascot_success.png", 150)
        top.addWidget(self.result_mascot)
        result_title_box = QVBoxLayout()
        self.result_title = QLabel("완주 결과")
        self.result_title.setObjectName("Title")
        self.result_player_label = QLabel("")
        self.result_player_label.setObjectName("Subtitle")
        result_title_box.addWidget(self.result_title)
        result_title_box.addWidget(self.result_player_label)
        top.addLayout(result_title_box, stretch=1)
        self.result_score_label = QLabel("0점")
        self.result_score_label.setObjectName("ScoreHero")
        top.addWidget(self.result_score_label)
        root.addLayout(top)

        summary = QHBoxLayout()
        summary.setSpacing(12)
        self.result_time_card = self._metric("시간", "-")
        self.result_accuracy_card = self._metric("정확도", "-")
        self.result_typo_card = self._metric("오타", "-")
        self.result_backspace_card = self._metric("Backspace", "-")
        for card in [
            self.result_time_card,
            self.result_accuracy_card,
            self.result_typo_card,
            self.result_backspace_card,
        ]:
            summary.addWidget(card)
        root.addLayout(summary)

        rank_card = self._card("Card")
        rank_layout = QVBoxLayout(rank_card)
        rank_layout.setContentsMargins(22, 18, 22, 18)
        rank_title = QLabel("리더보드 반영")
        rank_title.setObjectName("SectionTitleSmall")
        self.result_rank_label = QLabel("")
        self.result_rank_label.setObjectName("ResultSummary")
        self.result_rank_label.setWordWrap(True)
        rank_layout.addWidget(rank_title)
        rank_layout.addWidget(self.result_rank_label)
        root.addWidget(rank_card)

        self.result_summary = QLabel("")
        self.result_summary.setObjectName("HiddenSummary")

        actions = QHBoxLayout()
        actions.setSpacing(12)
        retry_button = QPushButton("다시 도전")
        retry_button.setMinimumHeight(46)
        retry_button.clicked.connect(self._start_game)
        leaderboard_button = QPushButton("리더보드")
        leaderboard_button.setMinimumHeight(46)
        leaderboard_button.clicked.connect(self._show_leaderboard)
        home_button = QPushButton("처음으로")
        home_button.setMinimumHeight(46)
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
        root.setSpacing(14)
        header = QHBoxLayout()
        header.setSpacing(16)
        header.addWidget(self._mascot_label("mascot_leaderboard.png", 82))
        title_box = QVBoxLayout()
        title = QLabel("리더보드")
        title.setObjectName("SectionTitle")
        self.leaderboard_subtitle = QLabel(f"행사 날짜 {self.event_date}")
        self.leaderboard_subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(self.leaderboard_subtitle)
        refresh_button = QPushButton("새로고침")
        refresh_button.clicked.connect(self._refresh_leaderboards)
        home_button = QPushButton("처음으로")
        home_button.clicked.connect(lambda: self.stack.setCurrentWidget(self.start_page))
        header.addLayout(title_box)
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
        self.leaderboard_language.setMinimumHeight(42)
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
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(38)
        return table

    def _make_admin_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(34)
        return table

    def _start_game(self) -> None:
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()
        language = self.language_input.currentText()
        if not name or not phone:
            QMessageBox.warning(self, "입력 필요", "이름과 전화번호를 입력해주세요.")
            return
        digit_count = sum(1 for ch in phone if ch.isdigit())
        if digit_count < 8:
            QMessageBox.warning(self, "전화번호 확인", "전화번호는 숫자 8자리 이상으로 입력해주세요.")
            self.phone_input.setFocus()
            return
        if self.snippet_load_error:
            QMessageBox.critical(self, "문제 파일 오류", self.snippet_load_error)
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
        self.game_subtitle.setText("공백, 대소문자, 줄바꿈까지 목표 코드와 같아야 합니다.")
        self.player_label.setText(f"참가자 {mask_name(self.current_name)}")
        self.snippet_label.setText(f"문제 {self.current_snippet.id}")
        self.code_highlighter.set_language(self.current_snippet.language)
        self.code_view.setPlainText(self.current_snippet.code)
        self.typing_input.setPlainText("")
        self.typing_input.setExtraSelections([])
        self.typing_input.setEnabled(True)
        self.submit_button.setEnabled(True)
        self.timer_label.setText("00.0s")
        self.progress.setValue(0)
        self.accuracy_label.setText("정확도 100.00%")
        self.typo_label.setText("오타 0")
        self.backspace_label.setText("Backspace 0")
        self.remaining_label.setText(f"남은 글자 {len(normalize_newlines(self.current_snippet.code))}")
        self.live_hint_label.setObjectName("Notice")
        self.live_hint_label.setText("키보드가 영문 입력 상태인지 확인해주세요.")
        self.live_hint_label.style().unpolish(self.live_hint_label)
        self.live_hint_label.style().polish(self.live_hint_label)
        self._set_mascot(self.game_mascot, "mascot_guide.png", 82)
        self.stack.setCurrentWidget(self.game_page)
        self.typing_input.setFocus()

    def _on_backspace(self) -> None:
        if self.finished:
            return
        self.backspace_count += 1
        self.backspace_label.setText(f"Backspace {self.backspace_count}")

    def _show_paste_blocked(self) -> None:
        self.statusBar().showMessage("붙여넣기는 사용할 수 없습니다.", 2500)

    def _set_notice(self, text: str, object_name: str = "Notice") -> None:
        self.live_hint_label.setText(text)
        if self.live_hint_label.objectName() != object_name:
            self.live_hint_label.setObjectName(object_name)
            self.live_hint_label.style().unpolish(self.live_hint_label)
            self.live_hint_label.style().polish(self.live_hint_label)

    def _update_live_feedback(self, expected: str, typed: str, typo_count: int) -> None:
        normalized_expected = normalize_newlines(expected)
        normalized_typed = normalize_newlines(typed)
        mismatch_index = _first_mismatch_index(normalized_expected, normalized_typed)
        selections: list[QTextEdit.ExtraSelection] = []
        if mismatch_index is not None and mismatch_index < len(normalized_typed):
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor("#7F1D1D"))
            selection.format.setForeground(QColor("#FEE2E2"))
            cursor = self.typing_input.textCursor()
            cursor.setPosition(mismatch_index)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
            selection.cursor = cursor
            selections.append(selection)
        self.typing_input.setExtraSelections(selections)

        if not normalized_typed:
            self._set_notice("첫 글자를 입력하면 타이머가 시작됩니다.")
            self._set_mascot(self.game_mascot, "mascot_guide.png", 82)
            return
        if mismatch_index is not None:
            line = normalized_typed.count("\n", 0, mismatch_index) + 1
            line_start = normalized_typed.rfind("\n", 0, mismatch_index) + 1
            column = mismatch_index - line_start + 1
            self._set_notice(f"{line}줄 {column}칸을 확인하세요. 공백과 기호도 점수에 반영됩니다.", "ErrorNotice")
            self._set_mascot(self.game_mascot, "mascot_typo.png", 82)
            return
        if typo_count == 0 and len(submission_text_for_comparison(typed)) >= len(normalized_expected):
            self._set_notice("완성입니다. 결과를 저장하고 있어요.", "SuccessNotice")
            self._set_mascot(self.game_mascot, "mascot_success.png", 82)
            return
        self._set_notice("좋아요. 그대로 이어서 입력하세요.")
        self._set_mascot(self.game_mascot, "mascot_guide.png", 82)

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
        self.remaining_label.setText(
            f"남은 글자 {max(0, len(normalize_newlines(expected)) - len(normalize_newlines(typed)))}"
        )
        self._update_live_feedback(expected, typed, typo_count)
        if is_submission_complete(expected, typed):
            self._finish_attempt()

    def _submit_attempt(self) -> None:
        if self.finished or self.current_snippet is None:
            return
        expected = self.current_snippet.code
        typed = self.typing_input.toPlainText()
        if is_submission_complete(expected, typed):
            self._finish_attempt()
            return
        self.statusBar().showMessage(self._submission_hint(expected, typed), 3500)

    def _submission_hint(self, expected: str, typed: str) -> str:
        normalized_expected = normalize_newlines(expected)
        normalized_typed = submission_text_for_comparison(typed)
        if len(normalized_typed) < len(normalized_expected):
            remaining = len(normalized_expected) - len(normalized_typed)
            return f"아직 {remaining}글자가 남았습니다. 공백과 줄바꿈까지 똑같이 입력해주세요."
        for index, (expected_ch, typed_ch) in enumerate(zip(normalized_expected, normalized_typed)):
            if expected_ch != typed_ch:
                line = normalized_typed.count("\n", 0, index) + 1
                line_start = normalized_typed.rfind("\n", 0, index) + 1
                column = index - line_start + 1
                return f"{line}줄 {column}칸이 목표 코드와 다릅니다. 공백/대소문자/기호를 확인해주세요."
        if len(normalized_typed) > len(normalized_expected):
            return f"목표보다 {len(normalized_typed) - len(normalized_expected)}글자가 더 입력되었습니다."
        return "목표 코드와 아직 일치하지 않습니다."

    def _finish_attempt(self) -> None:
        if self.current_snippet is None:
            return
        self.finished = True
        self.timer.stop()
        self.typing_input.setEnabled(False)
        self.submit_button.setEnabled(False)
        now = time.monotonic()
        started = self.started_at or now
        duration_ms = max(0, int((now - started) * 1000))
        expected = self.current_snippet.code
        typed = submission_text_for_comparison(self.typing_input.toPlainText())
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
        try:
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
        except Exception as exc:
            self.finished = False
            self.started_at = None
            self.timer_label.setText("00.0s")
            self.typing_input.setEnabled(True)
            self.submit_button.setEnabled(True)
            QMessageBox.critical(self, "기록 저장 실패", f"DB에 기록을 저장하지 못했습니다.\n{exc}")
            return
        self.last_score = score
        self.last_duration_ms = duration_ms
        self.last_accuracy = accuracy
        self.last_typo_count = typo_count
        display_name = mask_name(self.current_name)
        overall_rank = self.db.leaderboard_position(self.current_phone)
        today_rank = self.db.leaderboard_position(self.current_phone, event_date=self.event_date)
        language_rank = self.db.leaderboard_position(
            self.current_phone,
            language=self.current_snippet.language,
        )
        self.result_player_label.setText(
            f"{display_name} · {self.current_snippet.language} · {self.current_snippet.title}"
        )
        self.result_score_label.setText(f"{score:,}점")
        self._set_metric(self.result_time_card, f"{duration_ms / 1000:.2f}s")
        self._set_metric(self.result_accuracy_card, f"{accuracy:.2f}%")
        self._set_metric(self.result_typo_card, f"{typo_count}")
        self._set_metric(self.result_backspace_card, f"{self.backspace_count}")
        self.result_rank_label.setText(
            "\n".join(
                [
                    _rank_line("전체", overall_rank),
                    _rank_line("오늘", today_rank),
                    _rank_line(self.current_snippet.language, language_rank),
                ]
            )
        )
        if today_rank and today_rank["rank"] == 1:
            self._set_mascot(self.result_mascot, "mascot_highscore.png", 150)
        else:
            self._set_mascot(self.result_mascot, "mascot_success.png", 150)
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
        self.leaderboard_subtitle.setText(f"행사 날짜 {self.event_date}")
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
        self.leaderboard_subtitle.setText(f"행사 날짜 {self.event_date}")
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
        label.setMinimumSize(QSize(size, size))
        label.setMaximumSize(QSize(max(size, 260), max(size, 260)))
        self._set_mascot(label, filename, size)
        return label

    def _set_mascot(self, label: QLabel, filename: str, size: int) -> None:
        path = self.paths.assets_dir / "mascot" / filename
        if path.exists():
            cache_key = (filename, size)
            pixmap = self._pixmap_cache.get(cache_key)
            if pixmap is None:
                loaded = QPixmap(str(path))
                if loaded.isNull():
                    return
                pixmap = loaded.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._pixmap_cache[cache_key] = pixmap
            label.setPixmap(pixmap)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #090D16; color: #E7EDF7; font-size: 16px;
                font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Segoe UI", sans-serif;
            }
            QLabel#Title { font-size: 42px; font-weight: 900; color: #FFE66D; }
            QLabel#SectionTitle { font-size: 30px; font-weight: 900; color: #FFE66D; }
            QLabel#SectionTitleSmall { font-size: 21px; font-weight: 850; color: #F8FAFC; }
            QLabel#PanelTitle { font-size: 15px; font-weight: 800; color: #A7F3D0; }
            QLabel#Subtitle { color: #AAB6C9; }
            QLabel#Notice {
                color: #DDE7F5; background: #111827; border: 1px solid #263247;
                border-radius: 10px; padding: 10px 12px;
            }
            QLabel#ErrorNotice {
                color: #FEE2E2; background: #3B1118; border: 1px solid #C2410C;
                border-radius: 10px; padding: 10px 12px;
            }
            QLabel#SuccessNotice {
                color: #D1FAE5; background: #06281F; border: 1px solid #10B981;
                border-radius: 10px; padding: 10px 12px;
            }
            QLabel#DangerTitle { font-size: 20px; font-weight: 850; color: #FB7185; }
            QLabel#Timer { font-size: 34px; font-weight: 900; color: #34D399; }
            QLabel#ScoreHero { font-size: 52px; font-weight: 950; color: #34D399; }
            QLabel#ResultSummary { font-size: 22px; line-height: 150%; color: #DDE7F5; }
            QLabel#HiddenSummary { color: transparent; max-height: 0px; }
            QLabel#Mascot { font-size: 42px; color: #FFE66D; }
            QLabel#Chip, QLabel#AccentChip {
                background: #172033; color: #C7D2FE; border: 1px solid #31415F;
                border-radius: 14px; padding: 7px 12px; font-size: 13px; font-weight: 800;
            }
            QLabel#AccentChip { background: #3A2C08; color: #FFE66D; border-color: #8A6D12; }
            QLabel#LiveMetric {
                background: #0D1422; color: #E7EDF7; border: 1px solid #253149;
                border-radius: 10px; padding: 11px 12px; font-weight: 800;
            }
            QLabel#MetricTitle { color: #94A3B8; font-size: 13px; font-weight: 750; }
            QLabel#MetricValue { color: #F8FAFC; font-size: 23px; font-weight: 900; }
            QFrame#Card, QFrame#HeroCard, QFrame#SidePanel, QFrame#MetricCard, QFrame#DangerCard {
                background: #101827; border: 1px solid #24324A; border-radius: 14px;
            }
            QFrame#HeroCard { background: #0F1725; }
            QFrame#SidePanel { background: #0D1422; }
            QFrame#MetricCard { background: #111827; }
            QFrame#DangerCard { border-color: #7F1D1D; }
            QLineEdit, QComboBox, QPlainTextEdit, QDateEdit {
                background: #05070D; color: #F8FAFC; border: 1px solid #334155;
                border-radius: 10px; padding: 10px; selection-background-color: #FACC15;
                selection-color: #0B1020;
            }
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QDateEdit:focus {
                border: 1px solid #FACC15;
            }
            QPlainTextEdit#CodeBox { color: #D7DEE9; line-height: 145%; }
            QPlainTextEdit#InputBox { color: #FFE66D; line-height: 145%; }
            QPushButton {
                background: #182235; color: #F8FAFC; border: 1px solid #34445F;
                border-radius: 10px; padding: 10px 18px; font-weight: 800;
            }
            QPushButton:hover { background: #24324A; }
            QPushButton:pressed { background: #0F1725; }
            QPushButton#PrimaryButton { background: #FFE66D; color: #111827; border-color: #FFE66D; }
            QPushButton#PrimaryButton:hover { background: #FACC15; }
            QProgressBar {
                background: #05070D; border: 1px solid #334155; border-radius: 9px;
                text-align: center; color: #E7EDF7; font-weight: 800; min-height: 18px;
            }
            QProgressBar::chunk { background: #34D399; border-radius: 8px; }
            QTabWidget::pane { border: 1px solid #334155; border-radius: 10px; top: -1px; }
            QTabBar::tab {
                background: #111827; color: #AAB6C9; border: 1px solid #263247;
                padding: 10px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px;
            }
            QTabBar::tab:selected { color: #FFE66D; background: #172033; }
            QHeaderView::section {
                background: #101827; color: #FFE66D; padding: 9px; border: 0;
                font-weight: 850;
            }
            QTableWidget {
                background: #05070D; alternate-background-color: #0D1422;
                gridline-color: #1F2A44; selection-background-color: #24324A;
                selection-color: #F8FAFC;
            }
            QStatusBar#StatusBar { background: #05070D; color: #AAB6C9; }
            """
        )


def _first_mismatch_index(expected: str, typed: str) -> int | None:
    for index, (expected_ch, typed_ch) in enumerate(zip(expected, typed)):
        if expected_ch != typed_ch:
            return index
    if len(typed) > len(expected):
        return len(expected)
    return None


def _rank_line(label: str, row: dict[str, Any] | None) -> str:
    if row is None:
        return f"{label}: 아직 순위 없음"
    return f"{label}: {row['rank']}위 · 최고 {int(row['score']):,}점 · {row['duration_seconds']:.2f}s"


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
