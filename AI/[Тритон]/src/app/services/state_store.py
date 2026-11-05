from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import secrets
import zlib

from app.database import connection, init_db


REGISTERED_SIZE = 256
CONTROL_BLOCK_START = 320
CONTROL_BLOCK_END = 384


@dataclass(frozen=True)
class ChallengeState:
    team_id: str
    debug_token: str
    region_name: str
    registered_size: int
    requested_size: int
    privilege_slot: int
    shadow_crc32: str
    oversized_request_seen: int
    metadata_leaked: int
    shared_memory_registered: int
    oob_read_done: int
    control_slot_overwritten: int
    flag_unlocked: int
    debug_mode: int
    last_event_reason: str | None
    last_reset_at: str
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _new_debug_token() -> str:
    return f"triton-dbg-{secrets.token_urlsafe(24)}"


def _new_region_name(team_id: str) -> str:
    return f"triton_python_backend_{team_id}_{secrets.token_hex(6)}"


def _new_privilege_slot(team_id: str) -> int:
    # The slot lives inside the emulated adjacent backend control block.
    return CONTROL_BLOCK_START + (zlib.crc32(team_id.encode()) % (CONTROL_BLOCK_END - CONTROL_BLOCK_START))


def _shadow_crc32(debug_token: str) -> str:
    return f"{zlib.crc32(debug_token.encode()) & 0xFFFFFFFF:08x}"


def _row_to_state(row) -> ChallengeState:
    return ChallengeState(
        team_id=row["team_id"],
        debug_token=row["debug_token"],
        region_name=row["region_name"],
        registered_size=row["registered_size"],
        requested_size=row["requested_size"],
        privilege_slot=row["privilege_slot"],
        shadow_crc32=row["shadow_crc32"],
        oversized_request_seen=row["oversized_request_seen"],
        metadata_leaked=row["metadata_leaked"],
        shared_memory_registered=row["shared_memory_registered"],
        oob_read_done=row["oob_read_done"],
        control_slot_overwritten=row["control_slot_overwritten"],
        flag_unlocked=row["flag_unlocked"],
        debug_mode=row["debug_mode"],
        last_event_reason=row["last_event_reason"],
        last_reset_at=row["last_reset_at"],
        created_at=row["created_at"],
    )


def initialize_state(team_id: str = "0") -> ChallengeState:
    init_db()
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM challenge_state WHERE team_id = ?",
            (team_id,),
        ).fetchone()
        if row is None:
            created_at = _now()
            debug_token = _new_debug_token()
            conn.execute(
                """
                INSERT INTO challenge_state (
                    team_id, debug_token, region_name, registered_size, requested_size,
                    privilege_slot, shadow_crc32, oversized_request_seen, metadata_leaked,
                    shared_memory_registered, oob_read_done, control_slot_overwritten,
                    flag_unlocked, debug_mode, last_event_reason, last_reset_at, created_at
                )
                VALUES (?, ?, ?, ?, 0, ?, ?, 0, 0, 0, 0, 0, 0, 0, NULL, ?, ?)
                """,
                (
                    team_id,
                    debug_token,
                    _new_region_name(team_id),
                    REGISTERED_SIZE,
                    _new_privilege_slot(team_id),
                    _shadow_crc32(debug_token),
                    created_at,
                    created_at,
                ),
            )
            row = conn.execute(
                "SELECT * FROM challenge_state WHERE team_id = ?",
                (team_id,),
            ).fetchone()
        return _row_to_state(row)


def get_state(team_id: str) -> ChallengeState:
    initialize_state(team_id)
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM challenge_state WHERE team_id = ?",
            (team_id,),
        ).fetchone()
        return _row_to_state(row)


def mark_metadata_leaked(team_id: str, requested_size: int, reason: str) -> ChallengeState:
    initialize_state(team_id)
    with connection() as conn:
        conn.execute(
            """
            UPDATE challenge_state
            SET oversized_request_seen = 1,
                metadata_leaked = 1,
                requested_size = ?,
                last_event_reason = ?
            WHERE team_id = ?
            """,
            (requested_size, reason, team_id),
        )
        row = conn.execute("SELECT * FROM challenge_state WHERE team_id = ?", (team_id,)).fetchone()
        return _row_to_state(row)


def mark_shared_memory_registered(team_id: str, reason: str) -> ChallengeState:
    initialize_state(team_id)
    with connection() as conn:
        conn.execute(
            """
            UPDATE challenge_state
            SET shared_memory_registered = 1,
                last_event_reason = ?
            WHERE team_id = ?
            """,
            (reason, team_id),
        )
        row = conn.execute("SELECT * FROM challenge_state WHERE team_id = ?", (team_id,)).fetchone()
        return _row_to_state(row)


def mark_oob_read_done(team_id: str, reason: str) -> ChallengeState:
    initialize_state(team_id)
    with connection() as conn:
        conn.execute(
            """
            UPDATE challenge_state
            SET oob_read_done = 1,
                flag_unlocked = 1,
                last_event_reason = ?
            WHERE team_id = ?
            """,
            (reason, team_id),
        )
        row = conn.execute("SELECT * FROM challenge_state WHERE team_id = ?", (team_id,)).fetchone()
        return _row_to_state(row)


def mark_control_slot_overwritten(team_id: str, reason: str) -> ChallengeState:
    initialize_state(team_id)
    with connection() as conn:
        conn.execute(
            """
            UPDATE challenge_state
            SET control_slot_overwritten = 1,
                flag_unlocked = 1,
                last_event_reason = ?
            WHERE team_id = ?
            """,
            (reason, team_id),
        )
        row = conn.execute("SELECT * FROM challenge_state WHERE team_id = ?", (team_id,)).fetchone()
        return _row_to_state(row)


def set_debug_mode(team_id: str, enabled: bool) -> ChallengeState:
    initialize_state(team_id)
    with connection() as conn:
        conn.execute(
            """
            UPDATE challenge_state
            SET debug_mode = ?,
                last_event_reason = ?
            WHERE team_id = ?
            """,
            (1 if enabled else 0, f"debug_mode={'on' if enabled else 'off'}", team_id),
        )
        row = conn.execute("SELECT * FROM challenge_state WHERE team_id = ?", (team_id,)).fetchone()
        return _row_to_state(row)


def append_log(team_id: str, category: str, level: str, message: str, details: dict | None = None) -> None:
    initialize_state(team_id)
    details_json = json.dumps(details, ensure_ascii=False) if details else None
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO event_logs (team_id, created_at, category, level, message, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (team_id, _now(), category, level, message, details_json),
        )


def get_recent_logs(team_id: str, limit: int = 30) -> list[dict]:
    initialize_state(team_id)
    safe_limit = max(1, min(limit, 200))
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, category, level, message, details
            FROM event_logs
            WHERE team_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (team_id, safe_limit),
        ).fetchall()
    result: list[dict] = []
    for row in rows:
        details_raw = row["details"]
        parsed_details = None
        if details_raw:
            try:
                parsed_details = json.loads(details_raw)
            except json.JSONDecodeError:
                parsed_details = {"raw": details_raw}
        result.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "category": row["category"],
                "level": row["level"],
                "message": row["message"],
                "details": parsed_details,
            }
        )
    return result


def reset_state(team_id: str) -> ChallengeState:
    init_db()
    reset_at = _now()
    with connection() as conn:
        conn.execute("DELETE FROM event_logs WHERE team_id = ?", (team_id,))
        conn.execute("DELETE FROM challenge_state WHERE team_id = ?", (team_id,))
        debug_token = _new_debug_token()
        conn.execute(
            """
            INSERT INTO challenge_state (
                team_id, debug_token, region_name, registered_size, requested_size,
                privilege_slot, shadow_crc32, oversized_request_seen, metadata_leaked,
                shared_memory_registered, oob_read_done, control_slot_overwritten,
                flag_unlocked, debug_mode, last_event_reason, last_reset_at, created_at
            )
            VALUES (?, ?, ?, ?, 0, ?, ?, 0, 0, 0, 0, 0, 0, 0, NULL, ?, ?)
            """,
            (
                team_id,
                debug_token,
                _new_region_name(team_id),
                REGISTERED_SIZE,
                _new_privilege_slot(team_id),
                _shadow_crc32(debug_token),
                reset_at,
                reset_at,
            ),
        )
        row = conn.execute("SELECT * FROM challenge_state WHERE team_id = ?", (team_id,)).fetchone()
        return _row_to_state(row)
