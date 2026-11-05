from __future__ import annotations

from json import JSONDecodeError

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.auth_middleware import get_required_team
from app.services import debug, diagnostics, inference, shared_memory, state_store


router = APIRouter(prefix="/api")


def _team_id(team) -> str:
    return str(team.team_id)


@router.get("/models")
async def get_models(team=Depends(get_required_team)):
    state = state_store.get_state(_team_id(team))
    return {
        "models": inference.list_models(),
        "stages": debug.state_view(state),
    }


@router.post("/infer/{model_name}")
async def post_infer(model_name: str, request: Request, team=Depends(get_required_team)):
    payload = await _json_body(request)
    result = inference.infer(_team_id(team), model_name, payload)
    return JSONResponse(result.body, status_code=result.status_code)


@router.post("/shared-memory/read")
async def post_shared_memory_read(request: Request, team=Depends(get_required_team)):
    payload = await _json_body(request)
    result = shared_memory.read(_team_id(team), payload)
    return JSONResponse(result.body, status_code=result.status_code)


@router.post("/debug")
async def post_debug(request: Request, team=Depends(get_required_team)):
    payload = await _json_body(request)
    result = debug.run_debug_action(_team_id(team), payload)
    return JSONResponse(result.body, status_code=result.status_code)


@router.post("/debug-mode")
async def post_debug_mode(request: Request, team=Depends(get_required_team)):
    payload = await _json_body(request)
    result = diagnostics.set_debug_mode(_team_id(team), payload)
    return JSONResponse(result.body, status_code=result.status_code)


@router.get("/logs")
async def get_logs(team=Depends(get_required_team)):
    result = diagnostics.list_logs(_team_id(team))
    return JSONResponse(result.body, status_code=result.status_code)


@router.post("/reset")
async def post_reset(team=Depends(get_required_team)):
    state = state_store.reset_state(_team_id(team))
    return {
        "status": "reset",
        "team_id": state.team_id,
        "reset_at": state.last_reset_at,
        "stages": debug.state_view(state),
    }


async def _json_body(request: Request) -> dict:
    try:
        payload = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="тело запроса должно быть валидным JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="тело запроса должно быть JSON-объектом")
    return payload
