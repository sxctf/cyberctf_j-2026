import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from app.config import get_settings


_DB_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    db_path = get_settings().database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    with _DB_LOCK:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    with connection() as conn:
        _migrate_legacy_schema(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS challenge_state (
                team_id TEXT PRIMARY KEY,
                debug_token TEXT NOT NULL,
                region_name TEXT NOT NULL,
                registered_size INTEGER NOT NULL DEFAULT 256,
                requested_size INTEGER NOT NULL DEFAULT 0,
                privilege_slot INTEGER NOT NULL DEFAULT 0,
                shadow_crc32 TEXT NOT NULL DEFAULT '',
                oversized_request_seen INTEGER NOT NULL DEFAULT 0,
                metadata_leaked INTEGER NOT NULL DEFAULT 0,
                shared_memory_registered INTEGER NOT NULL DEFAULT 0,
                oob_read_done INTEGER NOT NULL DEFAULT 0,
                control_slot_overwritten INTEGER NOT NULL DEFAULT 0,
                flag_unlocked INTEGER NOT NULL DEFAULT 0,
                debug_mode INTEGER NOT NULL DEFAULT 0,
                last_event_reason TEXT,
                last_reset_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                category TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_logs_team_id_id ON event_logs(team_id, id)")


def _migrate_legacy_schema(conn: sqlite3.Connection) -> None:
    state_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(challenge_state)").fetchall()
    }
    if state_columns and "team_id" not in state_columns:
        conn.execute("DROP TABLE IF EXISTS challenge_state")
        conn.execute("DROP TABLE IF EXISTS event_logs")

