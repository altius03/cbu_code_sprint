from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QApplication: Any | None
MainWindow: Any | None
AppPaths: Any | None
try:
    QApplication = getattr(importlib.import_module("PySide6.QtWidgets"), "QApplication")
    MainWindow = getattr(importlib.import_module("cbu_code_sprint.app"), "MainWindow")
    AppPaths = getattr(importlib.import_module("cbu_code_sprint.paths"), "AppPaths")
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local GUI deps
    if exc.name == "PySide6":
        QApplication = None
        MainWindow = None
        AppPaths = None
    else:
        raise


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class GuiAdminTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert QApplication is not None
        cls.app = QApplication.instance() or QApplication([])

    def test_admin_screen_refreshes_participant_and_attempt_tables(self) -> None:
        assert MainWindow is not None
        assert AppPaths is not None
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            window = MainWindow(paths)
            try:
                window.db.record_attempt(
                    "홍길동",
                    "010-1111-2222",
                    "Python",
                    "2026-05-21",
                    "Python",
                    "python-001",
                    10_000,
                    100.0,
                    0,
                    0,
                    1020,
                )
                window.event_date = "2026-05-21"

                window._refresh_admin_stats()

                self.assertEqual(window.admin_participants_table.rowCount(), 1)
                self.assertEqual(window.admin_attempts_table.rowCount(), 1)
                self.assertEqual(window.admin_participants_table.item(0, 1).text(), "홍길동")
                self.assertEqual(window.admin_attempts_table.item(0, 2).text(), "010-1111-2222")
            finally:
                window.close()
                window.deleteLater()

    def test_game_completion_updates_result_rank_summary(self) -> None:
        assert MainWindow is not None
        assert AppPaths is not None
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            paths.snippets.write_text(
                """[
                  {
                    "id": "python-test",
                    "language": "Python",
                    "title": "Tiny",
                    "code": "print('CBU')"
                  }
                ]""",
                encoding="utf-8",
            )
            window = MainWindow(paths)
            try:
                window.name_input.setText("홍길동")
                window.phone_input.setText("010-1111-2222")
                window.language_input.setCurrentText("Python")

                window._start_game()
                window.typing_input.setPlainText("print('CBU')")
                self.app.processEvents()

                self.assertGreaterEqual(window.last_score, 1090)
                self.assertTrue(window.result_score_label.text().endswith("점"))
                self.assertIn("전체: 1위", window.result_rank_label.text())
                self.assertEqual(window.db.public_leaderboard(limit=10)[0]["display_name"], "홍*동")
            finally:
                window.close()
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()
