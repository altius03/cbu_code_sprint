from __future__ import annotations

import csv
import shutil
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .privacy import mask_name, normalize_phone

CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    phone_normalized TEXT NOT NULL UNIQUE,
    main_language TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    participant_id INTEGER NOT NULL REFERENCES participants(id),
    event_date TEXT NOT NULL,
    language TEXT NOT NULL,
    snippet_id TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    typo_count INTEGER NOT NULL,
    backspace_count INTEGER NOT NULL,
    score INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_event_date ON attempts(event_date);
CREATE INDEX IF NOT EXISTS idx_attempts_language ON attempts(language);
CREATE INDEX IF NOT EXISTS idx_attempts_score ON attempts(score DESC, accuracy DESC, duration_ms ASC);
"""


class Database:
    """Small SQLite repository for the portable leaderboard database."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(SCHEMA_SQL)
            connection.commit()

    def record_attempt(
        self,
        name: str,
        phone: str,
        main_language: str,
        event_date: str,
        language: str,
        snippet_id: str,
        duration_ms: int,
        accuracy: float,
        typo_count: int,
        backspace_count: int,
        score: int,
    ) -> int:
        clean_name = name.strip()
        clean_phone = phone.strip()
        phone_normalized = normalize_phone(clean_phone)
        clean_main_language = main_language.strip()
        clean_language = language.strip()
        clean_event_date = event_date.strip()
        if not clean_name:
            raise ValueError("name is required")
        if not phone_normalized:
            raise ValueError("phone is required")
        if not clean_main_language:
            raise ValueError("main_language is required")
        if not clean_language:
            raise ValueError("language is required")
        if not clean_event_date:
            raise ValueError("event_date is required")

        now = datetime.now().isoformat(timespec="seconds")
        with closing(self.connect()) as connection:
            existing = connection.execute(
                "SELECT id FROM participants WHERE phone_normalized = ?",
                (phone_normalized,),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO participants (name, phone, phone_normalized, main_language, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (clean_name, clean_phone, phone_normalized, clean_main_language, now),
                )
                participant_id_raw = cursor.lastrowid
                if participant_id_raw is None:
                    raise RuntimeError("failed to create participant")
                participant_id = int(participant_id_raw)
            else:
                participant_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE participants
                    SET name = ?, phone = ?, main_language = ?
                    WHERE id = ?
                    """,
                    (clean_name, clean_phone, clean_main_language, participant_id),
                )

            cursor = connection.execute(
                """
                INSERT INTO attempts (
                    participant_id, event_date, language, snippet_id, duration_ms, accuracy,
                    typo_count, backspace_count, score, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    participant_id,
                    clean_event_date,
                    clean_language,
                    snippet_id,
                    int(duration_ms),
                    float(accuracy),
                    int(typo_count),
                    int(backspace_count),
                    int(score),
                    now,
                ),
            )
            connection.commit()
            attempt_id = cursor.lastrowid
            if attempt_id is None:
                raise RuntimeError("failed to create attempt")
            return int(attempt_id)

    def public_leaderboard(
        self,
        *,
        limit: int = 10,
        event_date: str | None = None,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if event_date:
            where.append("a.event_date = ?")
            params.append(event_date)
        if language:
            where.append("a.language = ?")
            params.append(language)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        sql = f"""
        WITH ranked AS (
            SELECT
                p.name,
                p.main_language,
                a.event_date,
                a.language,
                a.snippet_id,
                a.duration_ms,
                a.accuracy,
                a.typo_count,
                a.backspace_count,
                a.score,
                a.created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY p.phone_normalized
                    ORDER BY a.score DESC, a.accuracy DESC, a.duration_ms ASC, a.created_at ASC
                ) AS row_number
            FROM attempts a
            JOIN participants p ON p.id = a.participant_id
            {where_sql}
        )
        SELECT * FROM ranked
        WHERE row_number = 1
        ORDER BY score DESC, accuracy DESC, duration_ms ASC, created_at ASC
        LIMIT ?
        """
        params.append(limit)
        with closing(self.connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._public_row(rank=index + 1, row=row) for index, row in enumerate(rows)]

    def leaderboard_position(
        self,
        phone: str,
        *,
        event_date: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the public leaderboard row for a participant's best scoped attempt."""

        phone_normalized = normalize_phone(phone)
        if not phone_normalized:
            return None

        where: list[str] = []
        params: list[Any] = []
        if event_date:
            where.append("a.event_date = ?")
            params.append(event_date)
        if language:
            where.append("a.language = ?")
            params.append(language)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        sql = f"""
        WITH ranked_attempts AS (
            SELECT
                p.phone_normalized,
                p.name,
                p.main_language,
                a.event_date,
                a.language,
                a.snippet_id,
                a.duration_ms,
                a.accuracy,
                a.typo_count,
                a.backspace_count,
                a.score,
                a.created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY p.phone_normalized
                    ORDER BY a.score DESC, a.accuracy DESC, a.duration_ms ASC, a.created_at ASC
                ) AS personal_rank
            FROM attempts a
            JOIN participants p ON p.id = a.participant_id
            {where_sql}
        ),
        leaders AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    ORDER BY score DESC, accuracy DESC, duration_ms ASC, created_at ASC
                ) AS leaderboard_rank
            FROM ranked_attempts
            WHERE personal_rank = 1
        )
        SELECT * FROM leaders
        WHERE phone_normalized = ?
        """
        params.append(phone_normalized)
        with closing(self.connect()) as connection:
            row = connection.execute(sql, params).fetchone()
        if row is None:
            return None
        return self._public_row(rank=int(row["leaderboard_rank"]), row=row)

    def participants(self) -> list[dict[str, Any]]:
        sql = """
        SELECT
            p.id,
            p.name,
            p.phone,
            p.phone_normalized,
            p.main_language,
            p.created_at,
            COUNT(a.id) AS attempt_count,
            MAX(a.score) AS best_score
        FROM participants p
        LEFT JOIN attempts a ON a.participant_id = p.id
        GROUP BY p.id, p.name, p.phone, p.phone_normalized, p.main_language, p.created_at
        ORDER BY p.created_at DESC, p.id DESC
        """
        with closing(self.connect()) as connection:
            rows = connection.execute(sql).fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "phone": row["phone"],
                "phone_normalized": row["phone_normalized"],
                "main_language": row["main_language"],
                "created_at": row["created_at"],
                "attempt_count": int(row["attempt_count"]),
                "best_score": int(row["best_score"]) if row["best_score"] is not None else None,
            }
            for row in rows
        ]

    def attempts(self, *, event_date: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE a.event_date = ?" if event_date else ""
        params: tuple[Any, ...] = (event_date,) if event_date else ()
        sql = f"""
        SELECT
            a.event_date, p.name, p.phone, p.main_language, a.language, a.score,
            a.duration_ms, a.accuracy, a.typo_count, a.backspace_count,
            a.snippet_id, a.created_at
        FROM attempts a
        JOIN participants p ON p.id = a.participant_id
        {where}
        ORDER BY a.created_at DESC, a.id DESC
        """
        with closing(self.connect()) as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def stats(self, *, event_date: str | None = None) -> dict[str, int | str]:
        target_date = event_date or date.today().isoformat()
        with closing(self.connect()) as connection:
            participants_total = connection.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
            attempts_total = connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            participants_today = connection.execute(
                """
                SELECT COUNT(DISTINCT p.phone_normalized)
                FROM attempts a
                JOIN participants p ON p.id = a.participant_id
                WHERE a.event_date = ?
                """,
                (target_date,),
            ).fetchone()[0]
            attempts_today = connection.execute(
                "SELECT COUNT(*) FROM attempts WHERE event_date = ?",
                (target_date,),
            ).fetchone()[0]
        return {
            "event_date": target_date,
            "participants_total": int(participants_total),
            "participants_today": int(participants_today),
            "attempts_total": int(attempts_total),
            "attempts_today": int(attempts_today),
        }

    def backup(self, backups_dir: str | Path) -> Path:
        self.initialize()
        destination_dir = Path(backups_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = destination_dir / f"leaderboard_{stamp}.sqlite"
        shutil.copy2(self.path, destination)
        return destination

    def export_public_leaderboard_csv(
        self,
        exports_dir: str | Path,
        *,
        event_date: str | None = None,
        language: str | None = None,
    ) -> Path:
        destination_dir = Path(exports_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        suffix_parts = [part for part in [event_date, language] if part]
        suffix = "_" + "_".join(part.replace(" ", "_") for part in suffix_parts) if suffix_parts else "_all"
        destination = destination_dir / f"cbu_code_sprint_public_leaderboard{suffix}.csv"
        rows = self.public_leaderboard(limit=10_000, event_date=event_date, language=language)
        fieldnames = [
            "rank",
            "event_date",
            "display_name",
            "main_language",
            "language",
            "score",
            "duration_ms",
            "accuracy",
        ]
        with destination.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: _csv_safe(row[field]) for field in fieldnames})
        return destination

    def export_all_attempts_csv(self, exports_dir: str | Path, *, event_date: str | None = None) -> Path:
        destination_dir = Path(exports_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"_{event_date}" if event_date else "_all"
        destination = destination_dir / f"cbu_code_sprint{suffix}.csv"
        rows = self.attempts(event_date=event_date)
        fieldnames = [
            "event_date",
            "name",
            "phone",
            "main_language",
            "language",
            "score",
            "duration_ms",
            "accuracy",
            "typo_count",
            "backspace_count",
            "snippet_id",
            "created_at",
        ]
        with destination.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: _csv_safe(row[field]) for field in fieldnames})
        return destination

    def delete_attempts_for_date(self, event_date: str) -> dict[str, int]:
        clean_event_date = event_date.strip()
        if not clean_event_date:
            raise ValueError("event_date is required")
        with closing(self.connect()) as connection:
            attempts_deleted = connection.execute(
                "DELETE FROM attempts WHERE event_date = ?",
                (clean_event_date,),
            ).rowcount
            orphan_participants_deleted = self._delete_orphan_participants(connection)
            connection.commit()
        return {
            "attempts_deleted": int(attempts_deleted),
            "orphan_participants_deleted": int(orphan_participants_deleted),
        }

    def reset_leaderboard(self) -> dict[str, int]:
        """Delete all attempts while keeping participant contact records for admin follow-up."""

        with closing(self.connect()) as connection:
            attempts_deleted = connection.execute("DELETE FROM attempts").rowcount
            connection.commit()
        return {"attempts_deleted": int(attempts_deleted)}

    def anonymize_personal_data(self) -> dict[str, int]:
        """Remove names/phones while preserving attempt rows for aggregate records."""

        with closing(self.connect()) as connection:
            rows = connection.execute("SELECT id FROM participants ORDER BY id").fetchall()
            for row in rows:
                participant_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE participants
                    SET name = ?, phone = ?, phone_normalized = ?
                    WHERE id = ?
                    """,
                    ("삭제된 참가자", "", f"deleted-{participant_id}", participant_id),
                )
            connection.commit()
        return {"participants_anonymized": len(rows)}

    def delete_all_data(self) -> dict[str, int]:
        with closing(self.connect()) as connection:
            attempts_deleted = connection.execute("DELETE FROM attempts").rowcount
            participants_deleted = connection.execute("DELETE FROM participants").rowcount
            connection.commit()
        return {
            "attempts_deleted": int(attempts_deleted),
            "participants_deleted": int(participants_deleted),
        }

    @staticmethod
    def _delete_orphan_participants(connection: sqlite3.Connection) -> int:
        return int(
            connection.execute(
                """
                DELETE FROM participants
                WHERE id NOT IN (SELECT DISTINCT participant_id FROM attempts)
                """
            ).rowcount
        )

    @staticmethod
    def _public_row(*, rank: int, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "rank": rank,
            "display_name": mask_name(str(row["name"])),
            "main_language": row["main_language"],
            "language": row["language"],
            "score": int(row["score"]),
            "duration_ms": int(row["duration_ms"]),
            "duration_seconds": round(int(row["duration_ms"]) / 1000, 2),
            "accuracy": float(row["accuracy"]),
            "typo_count": int(row["typo_count"]),
            "backspace_count": int(row["backspace_count"]),
            "event_date": row["event_date"],
            "event_date_label": _event_date_label(str(row["event_date"])),
            "snippet_id": row["snippet_id"],
        }


def _event_date_label(event_date: str) -> str:
    parts = event_date.split("-")
    if len(parts) == 3:
        return f"{parts[1]}/{parts[2]}"
    return event_date


def _csv_safe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.lstrip(" ").startswith(CSV_DANGEROUS_PREFIXES):
        return "'" + value
    return value
