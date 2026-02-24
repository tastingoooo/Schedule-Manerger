import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "schedule_manager.db"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS availabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                person_name TEXT NOT NULL,
                profession TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
            )
            """
        )

        availability_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(availabilities)").fetchall()
        }
        if "profession" not in availability_columns:
            conn.execute("ALTER TABLE availabilities ADD COLUMN profession TEXT")


def create_schedule(name: str, description: str | None = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO schedules (name, description) VALUES (?, ?)",
            (name.strip(), (description or "").strip() or None),
        )
        return cursor.lastrowid


def list_schedules() -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, description, created_at FROM schedules ORDER BY id DESC"
        ).fetchall()
    return rows


def update_schedule(schedule_id: int, name: str, description: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE schedules SET name = ?, description = ? WHERE id = ?",
            (name.strip(), (description or "").strip() or None, schedule_id),
        )


def delete_schedule(schedule_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))


def add_availability(
    schedule_id: int,
    person_name: str,
    profession: str | None,
    start_time: str,
    end_time: str,
    note: str | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO availabilities (schedule_id, person_name, profession, start_time, end_time, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                schedule_id,
                person_name.strip(),
                (profession or "").strip() or None,
                start_time,
                end_time,
                (note or "").strip() or None,
            ),
        )
        return cursor.lastrowid


def list_availabilities(schedule_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, schedule_id, person_name, profession, start_time, end_time, note, created_at
            FROM availabilities
            WHERE schedule_id = ?
            ORDER BY start_time ASC, person_name ASC
            """,
            (schedule_id,),
        ).fetchall()
    return rows


def update_availability(
    availability_id: int,
    person_name: str,
    profession: str | None,
    start_time: str,
    end_time: str,
    note: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE availabilities
            SET person_name = ?, profession = ?, start_time = ?, end_time = ?, note = ?
            WHERE id = ?
            """,
            (
                person_name.strip(),
                (profession or "").strip() or None,
                start_time,
                end_time,
                (note or "").strip() or None,
                availability_id,
            ),
        )


def delete_availability(availability_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM availabilities WHERE id = ?", (availability_id,))
