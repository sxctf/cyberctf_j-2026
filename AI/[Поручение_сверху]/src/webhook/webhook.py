"""
Gitea webhook listener for task05.
Receives webhook events → writes jobs to SQLite → agent picks them up.
Also acts as inter-service message bus (web portal reads job state from here).
"""
import asyncio
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import String, Text, DateTime, Boolean, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DB_PATH = os.environ.get("WEBHOOK_DB_PATH", "/data/webhook.db")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "ctf-webhook-secret")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI(title="task05-webhook", docs_url=None)

# SSE event bus
_subscribers: list[asyncio.Queue] = []
# Agent heartbeat (updated on every /jobs/next/pending poll)
_agent_last_seen: float = 0.0
_agent_llm_configured: bool = False


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    id:          Mapped[str]  = mapped_column(String(36), primary_key=True)
    team_id:     Mapped[str]  = mapped_column(String(64), default="", index=True)
    event_type:  Mapped[str]  = mapped_column(String(32))
    repo:        Mapped[str]  = mapped_column(String(128))
    issue_number:Mapped[int]  = mapped_column(Integer, default=0)
    issue_title: Mapped[str]  = mapped_column(Text, default="")
    issue_body:  Mapped[str]  = mapped_column(Text, default="")
    author:      Mapped[str]  = mapped_column(String(64), default="")
    status:      Mapped[str]  = mapped_column(String(32), default="queued")
    transcript:  Mapped[str]  = mapped_column(Text, default="")
    flag_found:  Mapped[bool] = mapped_column(Boolean, default=False)
    flag_value:  Mapped[str]  = mapped_column(Text, default="")
    flag_channel:Mapped[str]  = mapped_column(String(64), default="")
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                   default=lambda: datetime.now(UTC))
    completed_at:Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.body()

    # Verify HMAC signature
    sig_header = request.headers.get("X-Gitea-Signature", "")
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if sig_header and not hmac.compare_digest(sig_header, expected):
        raise HTTPException(400, "Invalid signature")

    event_type = request.headers.get("X-Gitea-Event", "unknown")
    payload = json.loads(body)

    # Only process issue/PR events on widget-public
    repo_full = payload.get("repository", {}).get("full_name", "")
    if "widget-public" not in repo_full:
        return {"status": "ignored", "reason": "not widget-public"}

    if event_type not in ("issues", "issue_comment", "pull_request"):
        return {"status": "ignored", "reason": "event type not tracked"}

    # Extract issue info
    issue = payload.get("issue") or payload.get("pull_request") or {}
    action = payload.get("action", "")
    if action not in ("opened", "created"):
        return {"status": "ignored", "reason": f"action={action}"}

    issue_body = issue.get("body", "") or ""
    # For comments, use comment body
    if event_type == "issue_comment":
        comment = payload.get("comment", {})
        issue_body = comment.get("body", "") or issue_body

    job_id = str(uuid.uuid4())
    async with Session() as session:
        job = Job(
            id=job_id,
            event_type=event_type,
            repo=repo_full,
            issue_number=issue.get("number", 0),
            issue_title=issue.get("title", ""),
            issue_body=issue_body[:8192],
            author=issue.get("user", {}).get("login", ""),
            status="queued",
        )
        session.add(job)
        await session.commit()

    # Notify SSE subscribers
    event_data = {"job_id": job_id, "event_type": event_type,
                  "issue_number": issue.get("number"), "author": job.author,
                  "status": "queued"}
    await _broadcast(event_data)
    return {"status": "queued", "job_id": job_id}


@app.get("/jobs")
async def list_jobs(team_id: str = "", limit: int = 50):
    async with Session() as session:
        q = select(Job).order_by(Job.created_at.desc()).limit(limit)
        if team_id:
            q = q.where(Job.team_id == team_id)
        result = await session.execute(q)
        return [_job_dict(j) for j in result.scalars().all()]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    async with Session() as session:
        job = await session.get(Job, job_id)
        if not job:
            raise HTTPException(404)
        return _job_dict(job)


@app.patch("/jobs/{job_id}")
async def update_job(job_id: str, request: Request):
    data = await request.json()
    async with Session() as session:
        job = await session.get(Job, job_id)
        if not job:
            raise HTTPException(404)
        for k, v in data.items():
            if hasattr(job, k):
                setattr(job, k, v)
        await session.commit()
    await _broadcast({"job_id": job_id, **data})
    return {"ok": True}


@app.get("/jobs/next/pending")
async def next_pending(request: Request):
    """Agent polls this to get the next job to process (heartbeat header)."""
    # Heartbeat: the portal uses this to show whether the agent is alive
    # and whether any LLM backend is configured.
    global _agent_last_seen, _agent_llm_configured
    import time as _time
    _agent_last_seen = _time.time()
    _agent_llm_configured = request.headers.get("x-agent-llm-configured") == "1"

    async with Session() as session:
        result = await session.execute(
            select(Job).where(Job.status == "queued")
            .order_by(Job.created_at.asc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if not job:
            return None
        job.status = "running"
        await session.commit()
        return _job_dict(job)


@app.get("/events")
async def sse_events(request: Request):
    """SSE stream for all job events."""
    from fastapi.responses import StreamingResponse
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)

    async def generator():
        yield ": connected\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _subscribers.remove(q)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/health")
def health():
    agent_seen_ago = None
    if _agent_last_seen:
        import time as _time
        agent_seen_ago = round(_time.time() - _agent_last_seen, 1)
    return {"status": "ok",
            "agent_seen_ago": agent_seen_ago,
            "agent_llm_configured": _agent_llm_configured}


async def _broadcast(data: dict):
    for q in list(_subscribers):
        await q.put(data)


def _job_dict(j: Job) -> dict:
    return {
        "id": j.id, "team_id": j.team_id, "event_type": j.event_type,
        "repo": j.repo, "issue_number": j.issue_number,
        "issue_title": j.issue_title, "issue_body": j.issue_body[:500],
        "author": j.author, "status": j.status,
        "transcript": j.transcript, "flag_found": j.flag_found,
        "flag_value": j.flag_value, "flag_channel": j.flag_channel,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("WEBHOOK_PORT", "8000")), log_level="info")
