from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from cbu_code_sprint.editor import INDENT_UNIT, indentation_for_newline, is_submission_complete
from cbu_code_sprint.locking import SingleInstanceError, SingleInstanceLock
from cbu_code_sprint.paths import AppPaths
from cbu_code_sprint.privacy import mask_name, normalize_phone
from cbu_code_sprint.scoring import ScoreInput, calculate_score
from cbu_code_sprint.snippets import load_snippets, snippets_for_language
from cbu_code_sprint.storage import Database


class UtilityTests(unittest.TestCase):
    def test_app_paths_resolve_everything_under_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            paths = AppPaths.from_home(home)

            self.assertEqual(paths.home, home.resolve())
            self.assertEqual(paths.database, home.resolve() / "data" / "leaderboard.sqlite")
            self.assertEqual(paths.config_dir, home.resolve() / "config")
            self.assertEqual(paths.assets_dir, home.resolve() / "assets")
            self.assertEqual(paths.exports_dir, home.resolve() / "exports")
            self.assertEqual(paths.backups_dir, home.resolve() / "backups")
            self.assertEqual(paths.lock_file, home.resolve() / "data" / "cbu_code_sprint.lock")

            paths.ensure_directories()
            for directory in [paths.data_dir, paths.config_dir, paths.assets_dir, paths.exports_dir, paths.backups_dir]:
                self.assertTrue(directory.is_dir())

    def test_mask_name_matches_public_leaderboard_policy(self) -> None:
        self.assertEqual(mask_name("홍길동"), "홍*동")
        self.assertEqual(mask_name("김현"), "김*")
        self.assertEqual(mask_name("Alex"), "A***")
        self.assertEqual(mask_name("A"), "A")
        self.assertEqual(mask_name("  홍길동  "), "홍*동")

    def test_normalize_phone_removes_formatting(self) -> None:
        self.assertEqual(normalize_phone("010-1111 2222"), "01011112222")
        self.assertEqual(normalize_phone("010.3333.4444"), "01033334444")
        self.assertEqual(normalize_phone(" +82 10-5555-6666 "), "821055556666")

    def test_calculate_score_uses_spec_formula_and_clamps(self) -> None:
        result = calculate_score(
            ScoreInput(duration_ms=10_000, accuracy=100.0, typo_count=2, backspace_count=3)
        )
        self.assertEqual(result, 967)

        low = calculate_score(
            ScoreInput(duration_ms=999_000, accuracy=40.0, typo_count=99, backspace_count=99)
        )
        self.assertEqual(low, 0)

    def test_snippet_loader_maps_unknown_language_to_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snippets.json"
            path.write_text(
                json.dumps(
                    [
                        {"id": "python-001", "language": "Python", "title": "Hello", "code": "print('hi')"},
                        {"id": "c-001", "language": "C", "title": "Hello", "code": "printf(\"hi\");"},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snippets = load_snippets(path)

        self.assertEqual([s.id for s in snippets_for_language(snippets, "아직 잘 모름")], ["python-001"])
        self.assertEqual([s.id for s in snippets_for_language(snippets, "C")], ["c-001"])

    def test_single_instance_lock_blocks_duplicate_acquisition_and_releases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "data" / "cbu_code_sprint.lock"

            with SingleInstanceLock(lock_path):
                self.assertTrue(lock_path.exists())
                with self.assertRaises(SingleInstanceError):
                    with SingleInstanceLock(lock_path):
                        pass

            with SingleInstanceLock(lock_path):
                self.assertTrue(lock_path.exists())

    def test_submission_accepts_exact_text_and_one_final_newline(self) -> None:
        expected = "def hello():\n    print('hi')"

        self.assertTrue(is_submission_complete(expected, expected))
        self.assertTrue(is_submission_complete(expected, expected + "\n"))
        self.assertTrue(is_submission_complete(expected, expected.replace("\n", "\r\n")))
        self.assertFalse(is_submission_complete(expected, expected + "    \n"))
        self.assertFalse(is_submission_complete(expected, expected.replace("hi", "bye")))

    def test_editor_auto_indent_matches_common_code_blocks(self) -> None:
        self.assertEqual(indentation_for_newline("if ok:", len("if ok:")), INDENT_UNIT)
        self.assertEqual(
            indentation_for_newline("    if ok:", len("    if ok:")),
            INDENT_UNIT * 2,
        )
        self.assertEqual(
            indentation_for_newline("    print(ok)", len("    print(ok)")),
            INDENT_UNIT,
        )
        self.assertEqual(indentation_for_newline("int main() {", len("int main() {")), INDENT_UNIT)


class DatabaseTests(unittest.TestCase):
    def test_database_records_attempts_and_public_leaderboard_dedupes_by_phone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()

            db.record_attempt(
                name="홍길동",
                phone="010-1111-2222",
                main_language="Python",
                event_date="2026-05-21",
                language="Python",
                snippet_id="python-001",
                duration_ms=30_000,
                accuracy=98.0,
                typo_count=1,
                backspace_count=2,
                score=800,
            )
            db.record_attempt(
                name="홍길동",
                phone="01011112222",
                main_language="Python",
                event_date="2026-05-21",
                language="Python",
                snippet_id="python-002",
                duration_ms=25_000,
                accuracy=100.0,
                typo_count=0,
                backspace_count=1,
                score=901,
            )
            db.record_attempt(
                name="Alex",
                phone="010-3333-4444",
                main_language="JavaScript",
                event_date="2026-05-21",
                language="JavaScript",
                snippet_id="javascript-001",
                duration_ms=24_000,
                accuracy=99.0,
                typo_count=1,
                backspace_count=0,
                score=870,
            )

            rows = db.public_leaderboard(limit=10)

        self.assertEqual([row["score"] for row in rows], [901, 870])
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["display_name"], "홍*동")
        self.assertEqual(rows[1]["display_name"], "A***")
        self.assertNotIn("phone", rows[0])
        self.assertNotIn("name", rows[0])

    def test_date_and_language_leaderboards_use_expected_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()

            db.record_attempt("김현", "010-0000-0000", "C", "2026-05-21", "C", "c-001", 40_000, 95.0, 2, 5, 700)
            db.record_attempt("김현", "01000000000", "C", "2026-05-22", "C", "c-002", 38_000, 97.0, 1, 3, 820)
            db.record_attempt("Jane", "010-9999-9999", "Java", "2026-05-22", "Java", "java-001", 32_000, 100.0, 0, 1, 900)

            date_rows = db.public_leaderboard(event_date="2026-05-21")
            c_rows = db.public_leaderboard(language="C")

        self.assertEqual(len(date_rows), 1)
        self.assertEqual(date_rows[0]["event_date"], "2026-05-21")
        self.assertEqual(date_rows[0]["display_name"], "김*")
        self.assertEqual([row["language"] for row in c_rows], ["C"])
        self.assertEqual(c_rows[0]["score"], 820)

    def test_leaderboard_position_returns_deduped_rank_for_participant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()

            db.record_attempt("홍길동", "010-1111-2222", "Python", "2026-05-21", "Python", "python-001", 40_000, 95.0, 2, 1, 700)
            db.record_attempt("홍길동", "01011112222", "Python", "2026-05-21", "Python", "python-002", 20_000, 100.0, 0, 0, 940)
            db.record_attempt("Alex", "010-3333-4444", "JavaScript", "2026-05-21", "JavaScript", "javascript-001", 18_000, 100.0, 0, 0, 960)

            position = db.leaderboard_position("010 1111 2222")
            python_position = db.leaderboard_position("010 1111 2222", language="Python")

        self.assertIsNotNone(position)
        self.assertEqual(position["rank"], 2)
        self.assertEqual(position["score"], 940)
        self.assertIsNotNone(python_position)
        self.assertEqual(python_position["rank"], 1)

    def test_csv_export_escapes_spreadsheet_formula_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()
            db.record_attempt(
                "=SUM(A1:A2)",
                "+82 10-1111-2222",
                "Python",
                "2026-05-21",
                "Python",
                " =python-001",
                10_000,
                100.0,
                0,
                0,
                1020,
            )

            all_csv = db.export_all_attempts_csv(paths.exports_dir, event_date="2026-05-21")
            public_csv = db.export_public_leaderboard_csv(paths.exports_dir, event_date="2026-05-21")

            with all_csv.open("r", encoding="utf-8-sig", newline="") as fh:
                all_rows = list(csv.DictReader(fh))
            with public_csv.open("r", encoding="utf-8-sig", newline="") as fh:
                public_rows = list(csv.DictReader(fh))

        self.assertEqual(all_rows[0]["name"], "'=SUM(A1:A2)")
        self.assertEqual(all_rows[0]["phone"], "'+82 10-1111-2222")
        self.assertEqual(all_rows[0]["snippet_id"], "' =python-001")
        self.assertTrue(public_rows[0]["display_name"].startswith("'="))

    def test_stats_backup_and_csv_export_are_usb_home_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()
            db.record_attempt("홍길동", "010-1111-2222", "Python", "2026-05-21", "Python", "python-001", 10_000, 100.0, 0, 0, 1020)

            stats = db.stats(event_date="2026-05-21")
            backup_path = db.backup(paths.backups_dir)
            csv_path = db.export_public_leaderboard_csv(paths.exports_dir, event_date="2026-05-21")

            with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))

            self.assertEqual(stats["participants_total"], 1)
            self.assertEqual(stats["attempts_today"], 1)
            self.assertTrue(backup_path.exists())
            self.assertTrue(str(backup_path).startswith(str(paths.backups_dir)))
            self.assertTrue(str(csv_path).startswith(str(paths.exports_dir)))
            self.assertEqual(rows[0]["display_name"], "홍*동")
            self.assertNotIn("phone", rows[0])

    def test_participants_returns_admin_contact_summary_without_attempt_duplication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()
            db.record_attempt("홍길동", "010-1111-2222", "Python", "2026-05-21", "Python", "python-001", 10_000, 100.0, 0, 0, 1020)
            db.record_attempt("홍길동", "01011112222", "Python", "2026-05-22", "Python", "python-002", 12_000, 98.0, 1, 0, 990)
            db.record_attempt("Alex", "010-3333-4444", "JavaScript", "2026-05-22", "JavaScript", "javascript-001", 14_000, 97.0, 2, 1, 870)

            participants = db.participants()

        self.assertEqual([row["name"] for row in participants], ["Alex", "홍길동"])
        self.assertEqual(participants[1]["phone"], "01011112222")
        self.assertEqual(participants[1]["attempt_count"], 2)
        self.assertEqual(participants[1]["best_score"], 1020)

    def test_delete_attempts_for_date_removes_only_that_day_and_orphans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()
            db.record_attempt("홍길동", "010-1111-2222", "Python", "2026-05-21", "Python", "python-001", 10_000, 100.0, 0, 0, 1020)
            db.record_attempt("홍길동", "010-1111-2222", "Python", "2026-05-22", "Python", "python-002", 11_000, 99.0, 1, 0, 990)
            db.record_attempt("Alex", "010-3333-4444", "JavaScript", "2026-05-21", "JavaScript", "javascript-001", 12_000, 98.0, 2, 0, 900)

            result = db.delete_attempts_for_date("2026-05-21")
            remaining_all = db.public_leaderboard(limit=10)
            remaining_deleted_day = db.public_leaderboard(limit=10, event_date="2026-05-21")
            stats = db.stats(event_date="2026-05-22")

        self.assertEqual(result["attempts_deleted"], 2)
        self.assertEqual(result["orphan_participants_deleted"], 1)
        self.assertEqual([row["event_date"] for row in remaining_all], ["2026-05-22"])
        self.assertEqual(remaining_deleted_day, [])
        self.assertEqual(stats["participants_total"], 1)

    def test_reset_leaderboard_deletes_attempts_but_keeps_participants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()
            db.record_attempt("홍길동", "010-1111-2222", "Python", "2026-05-21", "Python", "python-001", 10_000, 100.0, 0, 0, 1020)

            result = db.reset_leaderboard()
            stats = db.stats(event_date="2026-05-21")

        self.assertEqual(result["attempts_deleted"], 1)
        self.assertEqual(stats["participants_total"], 1)
        self.assertEqual(stats["attempts_total"], 0)

    def test_anonymize_personal_data_removes_names_and_phones_without_deleting_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()
            db.record_attempt("홍길동", "010-1111-2222", "Python", "2026-05-21", "Python", "python-001", 10_000, 100.0, 0, 0, 1020)
            db.record_attempt("Alex", "010-3333-4444", "JavaScript", "2026-05-21", "JavaScript", "javascript-001", 12_000, 98.0, 2, 0, 900)

            result = db.anonymize_personal_data()
            attempts = db.attempts()
            leaderboard = db.public_leaderboard(limit=10)

        self.assertEqual(result["participants_anonymized"], 2)
        self.assertEqual({row["name"] for row in attempts}, {"삭제된 참가자"})
        self.assertEqual({row["phone"] for row in attempts}, {""})
        self.assertEqual(len(leaderboard), 2)
        self.assertEqual({row["display_name"] for row in leaderboard}, {"삭*****자"})

    def test_delete_all_data_removes_participants_and_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.from_home(Path(tmp))
            paths.ensure_directories()
            db = Database(paths.database)
            db.initialize()
            db.record_attempt("홍길동", "010-1111-2222", "Python", "2026-05-21", "Python", "python-001", 10_000, 100.0, 0, 0, 1020)

            result = db.delete_all_data()
            stats = db.stats(event_date="2026-05-21")
            leaderboard = db.public_leaderboard(limit=10)

        self.assertEqual(result["attempts_deleted"], 1)
        self.assertEqual(result["participants_deleted"], 1)
        self.assertEqual(stats["participants_total"], 0)
        self.assertEqual(stats["attempts_total"], 0)
        self.assertEqual(leaderboard, [])


if __name__ == "__main__":
    unittest.main()
