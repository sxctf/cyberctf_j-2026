from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.services import state_store
from app.services.inference import ServiceResponse


ALLOWED_ACTIONS = {"dump_runtime", "diagnostics"}


def run_debug_action(team_id: str, payload: dict[str, Any]) -> ServiceResponse:
    token = payload.get("token") or payload.get("debug_token")
    action = payload.get("action", "dump_runtime")

    if not isinstance(token, str):
        return ServiceResponse({"error": "требуется debug_token"}, 401)
    if action not in ALLOWED_ACTIONS:
        return ServiceResponse({"error": f"неподдерживаемое debug-действие '{action}'"}, 400)

    state = state_store.get_state(team_id)
    if not _constant_time_equal(token, state.debug_token):
        return ServiceResponse({"error": "некорректный debug_token"}, 403)
    if state.flag_unlocked <= 0:
        return ServiceResponse(
            {
                "error": "debug-действие закрыто; backend control block еще не раскрыт",
            },
            403,
        )

    return ServiceResponse(
        {
            "status": "ok",
            "action": action,
            "diagnostics": {
                "backend": "triton_python_backend",
                "runtime": "tritonwebmid-internal",
                "region_name": state.region_name,
                "debug_mode": bool(state.debug_mode),
                "stages": state_view(state),
            },
            "flag": get_settings().flag,
        }
    )


def state_view(state: state_store.ChallengeState) -> dict[str, bool]:
    return {
        "oversized_request_seen": bool(state.oversized_request_seen),
        "metadata_leaked": bool(state.metadata_leaked),
        "oob_read_done": bool(state.oob_read_done),
        "flag_unlocked": bool(state.flag_unlocked),
    }


def _constant_time_equal(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    result = 0
    for left_char, right_char in zip(left.encode(), right.encode(), strict=True):
        result |= left_char ^ right_char
    return result == 0
