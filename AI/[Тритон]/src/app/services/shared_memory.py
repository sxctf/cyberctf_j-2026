from __future__ import annotations

from typing import Any

from app.services import state_store
from app.services.inference import ServiceResponse


PUBLIC_BYTE = "41"


def read(team_id: str, payload: dict[str, Any]) -> ServiceResponse:
    state = state_store.get_state(team_id)
    region_name = payload.get("region_name")
    offset = _as_int(payload.get("offset"), default=-1)
    byte_size = _as_int(payload.get("byte_size"), default=-1)

    if state.metadata_leaked <= 0:
        return ServiceResponse(
            {"error": "read отклонен: сначала нужен metadata leak shared-memory региона"},
            403,
        )
    if region_name != state.region_name:
        return ServiceResponse({"error": "неизвестный shared-memory регион"}, 404)
    if offset < 0 or byte_size <= 0:
        return ServiceResponse({"error": "offset и byte_size должны описывать положительный диапазон"}, 400)

    end = offset + byte_size
    if end <= state.registered_size:
        state_store.append_log(
            team_id,
            category="shared_memory",
            level="info",
            message="чтение в границах shared memory завершено",
            details={"offset": offset, "byte_size": byte_size},
        )
        return ServiceResponse(
            {
                "status": "read",
                "region_name": state.region_name,
                "offset": offset,
                "byte_size": byte_size,
                "data_hex": PUBLIC_BYTE * byte_size,
                "classification": "public_tensor_region",
            }
        )

    if not _overlaps_control_block(offset, end):
        state_store.append_log(
            team_id,
            category="shared_memory",
            level="warning",
            message="OOB read не попал в соседний control block",
            details={
                "offset": offset,
                "byte_size": byte_size,
                "registered_size": state.registered_size,
                "requested_span": [offset, end],
            },
        )
        return ServiceResponse(
            {
                "error": "read-диапазон вышел за публичный регион, но не вернул полезные backend-данные",
                "registered_size": state.registered_size,
                "requested_span": [offset, end],
                "control_block": [state_store.CONTROL_BLOCK_START, state_store.CONTROL_BLOCK_END],
            },
            422,
        )

    updated = state_store.mark_oob_read_done(team_id, "oob_adjacent_control_block_read")
    state_store.append_log(
        team_id,
        category="shared_memory",
        level="critical",
        message="соседний control block раскрыт через OOB read",
        details={
            "offset": offset,
            "byte_size": byte_size,
            "registered_size": updated.registered_size,
            "requested_span": [offset, end],
        },
    )
    return ServiceResponse(
        {
            "status": "oob_read",
            "region_name": updated.region_name,
            "offset": offset,
            "byte_size": byte_size,
            "disclosure": {
                "debug_token": updated.debug_token,
                "classification": "backend_control_block",
            },
        }
    )


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _overlaps_control_block(start: int, end: int) -> bool:
    return start < state_store.CONTROL_BLOCK_END and end > state_store.CONTROL_BLOCK_START
