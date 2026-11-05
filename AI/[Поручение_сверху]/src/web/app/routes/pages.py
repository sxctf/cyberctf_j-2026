"""HTML pages for task05 portal."""
import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..auth_middleware import get_optional_team, get_required_team
from ..templating import templates

WEBHOOK_URL      = os.environ.get("WEBHOOK_URL", "http://127.0.0.1:8200")
GITEA_URL        = os.environ.get("GITEA_URL", "http://127.0.0.1:8202")
GITEA_PUBLIC_URL = os.environ.get("GITEA_PUBLIC_URL", "http://localhost:8202")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, team=Depends(get_optional_team)):
    # Agent heartbeat from the webhook queue: warn when the worker is down
    # or no LLM backend is configured (jobs would just fail).
    agent_alive = False
    llm_ready = None
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{WEBHOOK_URL}/health")
            if r.status_code == 200:
                data = r.json()
                seen = data.get("agent_seen_ago")
                agent_alive = seen is not None and seen < 30
                llm_ready = data.get("agent_llm_configured")
    except Exception:
        pass
    return templates.TemplateResponse(request, "index.html", {
        "team": team, "gitea_url": GITEA_PUBLIC_URL,
        "agent_alive": agent_alive, "llm_ready": llm_ready,
    })


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, team=Depends(get_optional_team)):
    return templates.TemplateResponse(request, "setup.html", {
        "team": team, "gitea_url": GITEA_PUBLIC_URL,
    })


@router.post("/setup/create-account")
async def create_account(request: Request, team=Depends(get_required_team)):
    from ..core.gitea_client import create_team_account
    try:
        result = await create_team_account(team.team_name)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/activity", response_class=HTMLResponse)
async def activity_page(request: Request, team=Depends(get_optional_team)):
    return templates.TemplateResponse(request, "activity.html", {
        "team": team, "gitea_url": GITEA_PUBLIC_URL,
    })


@router.get("/runs/{job_id}", response_class=HTMLResponse)
async def run_detail(job_id: str, request: Request, team=Depends(get_optional_team)):
    try:
        async with httpx.AsyncClient(base_url=WEBHOOK_URL, timeout=5) as client:
            r = await client.get(f"/jobs/{job_id}")
            job = r.json() if r.status_code == 200 else {}
    except Exception:
        job = {}
    return templates.TemplateResponse(request, "run_detail.html", {
        "team": team, "job": job, "gitea_url": GITEA_PUBLIC_URL,
    })


@router.get("/inbox", response_class=HTMLResponse)
async def inbox_page(request: Request, team=Depends(get_optional_team)):
    # Fetch bot comments and commits from Gitea
    from ..core.gitea_client import get_public_comments, get_bot_commits
    import re
    FLAG_PATTERN = re.compile(r"FLAG\{[^}]+\}")

    comments = []
    commits  = []
    try:
        comments = await get_public_comments()
        commits  = await get_bot_commits()
    except Exception:
        pass

    # Annotate with flag detection
    for c in comments:
        c["flag_match"] = FLAG_PATTERN.findall(c.get("body", ""))
    for c in commits:
        msg = c.get("commit", {}).get("message", "")
        c["flag_match"] = FLAG_PATTERN.findall(msg)

    return templates.TemplateResponse(request, "inbox.html", {
        "team": team, "comments": comments, "commits": commits,
 "gitea_url": GITEA_PUBLIC_URL,
    })
