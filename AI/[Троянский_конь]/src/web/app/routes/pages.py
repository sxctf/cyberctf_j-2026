"""HTML page routes for task03."""
import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.jobs import Job, get_session
from ..templating import templates
from ..auth_middleware import get_optional_team

SANDBOX_URL = os.environ.get("SANDBOX_URL", "http://127.0.0.1:8102")
router = APIRouter()


async def _sandbox_isolation() -> str:
    """Report the loader containment mode so the UI can warn organizers."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{SANDBOX_URL}/health")
            return r.json().get("isolation", "unknown")
    except Exception:
        return "unknown"


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, team=Depends(get_optional_team)):
    return templates.TemplateResponse(request, "index.html", {
        "team": team,
    })


@router.get("/submit", response_class=HTMLResponse)
async def submit_page(request: Request, team=Depends(get_optional_team)):
    return templates.TemplateResponse(request, "submit.html", {
        "team": team,
        "isolation": await _sandbox_isolation(),
    })


@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    team=Depends(get_optional_team),
):
    jobs = []
    if team:
        result = await session.execute(
            select(Job)
            .where(Job.team_id == str(team.team_id))
            .order_by(Job.created_at.desc())
            .limit(50)
        )
        jobs = result.scalars().all()
    return templates.TemplateResponse(request, "history.html", {
        "team": team, "jobs": jobs,
    })


@router.get("/dns-log", response_class=HTMLResponse)
async def dns_log_page(request: Request, team=Depends(get_optional_team)):
    return templates.TemplateResponse(request, "dns_log.html", {
        "team": team,
    })
