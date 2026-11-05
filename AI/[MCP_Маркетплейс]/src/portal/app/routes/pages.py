"""HTML pages for task07 portal."""
import json
import os

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth_middleware import get_optional_team
from ..templating import templates

ORCH_URL  = os.environ.get("ORCH_URL",  "http://127.0.0.1:8314")
EXFIL_URL = os.environ.get("EXFIL_URL", "http://127.0.0.1:8312")

router = APIRouter()


def _client(timeout: float = 5) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=ORCH_URL, timeout=timeout)


async def _get_submission(team_id: str) -> dict | None:
    try:
        async with _client() as client:
            r = await client.get(f"/submissions/{team_id}")
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def _get_runs(team_id: str, limit: int = 20) -> list:
    try:
        async with _client() as client:
            r = await client.get(f"/runs?team_id={team_id}&limit={limit}")
            return r.json() if r.status_code == 200 else []
    except Exception:
        return []


async def _llm_status() -> bool | None:
    """None = unknown (orchestrator down), False = LLM not configured."""
    try:
        async with _client(timeout=2) as client:
            r = await client.get("/health")
            data = r.json()
            return data.get("llm_configured")
    except Exception:
        return None


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, team=Depends(get_optional_team)):
    submission = None
    runs = []
    llm_ready = await _llm_status()
    if team:
        submission = await _get_submission(str(team.team_id))
        runs = await _get_runs(str(team.team_id))
    return templates.TemplateResponse(request, "index.html", {
        "team": team, "submission": submission, "runs": runs,
        "exfil_base": EXFIL_URL, "llm_ready": llm_ready,
    })


@router.get("/tool", response_class=HTMLResponse)
async def tool_editor(request: Request,
                      team=Depends(get_optional_team),
                      saved: str = "", error: str = ""):
    submission = None
    if team:
        submission = await _get_submission(str(team.team_id))
    return templates.TemplateResponse(request, "tool_editor.html", {
        "team": team, "submission": submission,
        "saved": bool(saved), "error": bool(error),
    })


@router.post("/tool")
async def submit_tool(
    request: Request,
    team=Depends(get_optional_team),
    tool_name: str = Form(...),
    tool_description: str = Form(...),
    tool_schema: str = Form("{}"),
    tool_response: str = Form(""),
):
    if not team:
        return RedirectResponse("/", status_code=303)
    try:
        schema = json.loads(tool_schema)
    except Exception:
        schema = {}
    try:
        async with _client(timeout=10) as client:
            r = await client.post("/submissions", json={
                "team_id": str(team.team_id),
                "tool_name": tool_name,
                "tool_description": tool_description,
                "tool_schema": schema,
                "tool_response": tool_response,
            })
        if r.status_code == 201:
            return RedirectResponse("/tool?saved=1", status_code=303)
    except Exception:
        pass
    return RedirectResponse("/tool?error=1", status_code=303)


@router.get("/marketplace", response_class=HTMLResponse)
async def marketplace(request: Request, team=Depends(get_optional_team)):
    """Catalog of MCP servers: built-ins + community submissions."""
    catalog = {"builtin": [], "community": [], "endpoint": ""}
    try:
        async with _client() as client:
            r = await client.get("/catalog")
            if r.status_code == 200:
                catalog = r.json()
    except Exception:
        pass
    return templates.TemplateResponse(request, "marketplace.html", {
        "team": team, "catalog": catalog,
    })


@router.post("/runs")
async def trigger_run(
    request: Request,
    team=Depends(get_optional_team),
    task_variant: int = Form(0),
):
    if not team:
        return RedirectResponse("/", status_code=303)
    try:
        async with _client(timeout=10) as client:
            r = await client.post("/runs", json={
                "team_id": str(team.team_id),
                "task_variant": task_variant,
            })
        if r.status_code == 201:
            data = r.json()
            return RedirectResponse(f"/runs/{data['session_id']}", status_code=303)
    except Exception:
        pass
    return RedirectResponse("/", status_code=303)


@router.get("/runs/{session_id}", response_class=HTMLResponse)
async def run_detail(session_id: str, request: Request, team=Depends(get_optional_team)):
    run = {}
    exfil_logs = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{ORCH_URL}/runs/{session_id}")
            if r.status_code == 200:
                run = r.json()
            # Exfil listener logs are keyed by team id (the exfil URL handed
            # to the agent embeds it).
            if run.get("team_id"):
                r2 = await client.get(f"{EXFIL_URL}/logs/{run['team_id']}?limit=50")
                if r2.status_code == 200:
                    exfil_logs = r2.json()
    except Exception:
        pass
    return templates.TemplateResponse(request, "run_detail.html", {
        "team": team, "run": run, "session_id": session_id,
        "exfil_logs": exfil_logs,
    })


@router.get("/api/runs/{session_id}")
async def api_run(session_id: str):
    """JSON endpoint — polled by run_detail page for status updates."""
    try:
        async with _client() as client:
            r = await client.get(f"/runs/{session_id}")
            return r.json() if r.status_code == 200 else {"status": "error"}
    except Exception:
        return {"status": "error"}


@router.get("/exfil", response_class=HTMLResponse)
async def exfil_log(request: Request, team=Depends(get_optional_team)):
    logs = []
    if team:
        try:
            async with httpx.AsyncClient(base_url=EXFIL_URL, timeout=5) as client:
                r = await client.get(f"/logs/{team.team_id}?limit=100")
                if r.status_code == 200:
                    logs = r.json()
        except Exception:
            pass
    return templates.TemplateResponse(request, "exfil_log.html", {
        "team": team, "logs": logs,
        "exfil_base": EXFIL_URL,
    })
