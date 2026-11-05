from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock


SESSION_TIMEOUT_MINUTES = 10


@dataclass
class RuntimeState:
    request_count: int
    last_reset_at: str
    first_request_at: float | None = field(default=None)


_LOCK = Lock()
_STATE: RuntimeState | None = None


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def initialize_state() -> RuntimeState:
    global _STATE
    with _LOCK:
        if _STATE is None:
            _STATE = RuntimeState(request_count=0, last_reset_at=_now_iso())
        return _STATE


def get_state() -> RuntimeState:
    state = initialize_state()
    return RuntimeState(
        request_count=state.request_count,
        last_reset_at=state.last_reset_at,
        first_request_at=state.first_request_at,
    )


def next_request_id() -> str:
    global _STATE
    with _LOCK:
        if _STATE is None:
            _STATE = RuntimeState(request_count=0, last_reset_at=_now_iso())
        state = _STATE
        state.request_count += 1
        if state.first_request_at is None:
            state.first_request_at = datetime.now(UTC).timestamp()
        _STATE = state
        return f"prc-{state.request_count:04d}"


def session_expired() -> bool:
    with _LOCK:
        if _STATE is None or _STATE.first_request_at is None:
            return False
        elapsed = datetime.now(UTC).timestamp() - _STATE.first_request_at
        return elapsed >= SESSION_TIMEOUT_MINUTES * 60


def session_remaining_seconds() -> int:
    with _LOCK:
        if _STATE is None or _STATE.first_request_at is None:
            return SESSION_TIMEOUT_MINUTES * 60
        elapsed = datetime.now(UTC).timestamp() - _STATE.first_request_at
        remaining = max(0, int(SESSION_TIMEOUT_MINUTES * 60 - elapsed))
        return remaining


def reset_state() -> RuntimeState:
    global _STATE
    with _LOCK:
        _STATE = RuntimeState(request_count=0, last_reset_at=_now_iso())
        return _STATE


def _set_first_request_at_ts(timestamp: float) -> None:
    global _STATE
    with _LOCK:
        if _STATE is None:
            _STATE = RuntimeState(request_count=0, last_reset_at=_now_iso())
        _STATE.first_request_at = timestamp
