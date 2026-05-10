import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "notes_tracker.db"
SAVED_DIR = ROOT / "backend" / "saved"
NOTES_DIR = ROOT / "notes"


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS captures (
                stem            TEXT PRIMARY KEY,
                detected_at     TEXT NOT NULL,
                note_created    INTEGER NOT NULL DEFAULT 0,
                note_created_at TEXT,
                input_tokens    INTEGER,
                output_tokens   INTEGER
            )
        """)
        # migrate existing tables that predate the token columns
        for col, typ in [("input_tokens", "INTEGER"), ("output_tokens", "INTEGER")]:
            try:
                conn.execute(f"ALTER TABLE captures ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass  # column already exists


def sync_saved_folder():
    """Insert any .txt files in backend/saved/ not yet in the DB."""
    with _conn() as conn:
        for path in SAVED_DIR.glob("*.txt"):
            conn.execute(
                "INSERT OR IGNORE INTO captures (stem, detected_at) VALUES (?, ?)",
                (path.stem, datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()),
            )


def sync_notes_folder():
    """Mark stems that already have a corresponding .md in notes/ as done."""
    if not NOTES_DIR.exists():
        return
    with _conn() as conn:
        for path in NOTES_DIR.glob("*.md"):
            conn.execute(
                """UPDATE captures
                      SET note_created = 1,
                          note_created_at = ?
                    WHERE stem = ? AND note_created = 0""",
                (datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(), path.stem),
            )


def get_files_without_notes() -> list[str]:
    """Return stems of captures that have no note yet, oldest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT stem FROM captures WHERE note_created = 0 ORDER BY detected_at"
        ).fetchall()
    return [r[0] for r in rows]


def mark_note_created(stem: str, input_tokens: int | None = None, output_tokens: int | None = None):
    with _conn() as conn:
        conn.execute(
            """UPDATE captures
                  SET note_created    = 1,
                      note_created_at = ?,
                      input_tokens    = ?,
                      output_tokens   = ?
                WHERE stem = ?""",
            (datetime.now(tz=timezone.utc).isoformat(), input_tokens, output_tokens, stem),
        )
