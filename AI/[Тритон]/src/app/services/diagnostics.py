from __future__ import annotations

from typing import Any

from app.services import state_store
from app.services.debug import state_view
from app.services.inference import ServiceResponse


def set_debug_mode(team_id: str, payload: dict[str, Any]) -> ServiceResponse:
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return ServiceResponse({"error": "поле enabled должно быть boolean"}, 400)

    state = state_store.set_debug_mode(team_id, enabled)
    state_store.append_log(
        team_id,
        category="debug_mode",
        level="info",
        message="режим debug переключен",
        details={"enabled": enabled},
    )
    return ServiceResponse(
        {
            "status": "ok",
            "debug_mode": bool(state.debug_mode),
            "stages": state_view(state),
        }
    )


def list_logs(team_id: str, limit: int = 30) -> ServiceResponse:
    state = state_store.get_state(team_id)
    logs = state_store.get_recent_logs(team_id, limit=limit)
    return ServiceResponse(
        {
            "logs": logs,
            "debug_mode": bool(state.debug_mode),
            "stages": state_view(state),
        }
    )
