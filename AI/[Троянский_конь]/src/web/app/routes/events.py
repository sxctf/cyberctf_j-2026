"""SSE endpoints for real-time job status updates and DNS log."""
import asyncio
import json
import os
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..auth_middleware import get_required_team, get_optional_team
from ..core.jobs import get_event_queue

router = APIRouter(prefix="/events")

DNS_LOGGER_URL = os.environ.get("DNS_LOGGER_URL", "http://task03-dns:8053")


@router.get("/jobs/{job_id}")
async def job_events(job_id: str, team=Depends(get_required_team)):
    """SSE stream of processing events for a specific job."""

    async def generator() -> AsyncGenerator[str, None]:
        q = get_event_queue(job_id)
        # Send keep-alive comment first
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
                # If terminal state, close stream
                if event.get("step") in ("done", "scan_blocked", "error"):
                    break
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/dns")
async def dns_events(team=Depends(get_optional_team)):
    """SSE stream forwarding from dns-logger service."""

    async def generator() -> AsyncGenerator[str, None]:
        yield ": connected\n\n"
        last_ts = ""
        while True:
            try:
                async with httpx.AsyncClient(base_url=DNS_LOGGER_URL, timeout=5.0) as client:
                    params = {"limit": 50}
                    if last_ts:
                        params["since_ts"] = last_ts
                    resp = await client.get("/queries", params=params)
                    entries = resp.json()
                    if entries:
                        last_ts = entries[0]["ts"]
                        for entry in reversed(entries):
                            yield f"data: {json.dumps(entry)}\n\n"
            except Exception:
                pass
            await asyncio.sleep(1.0)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
