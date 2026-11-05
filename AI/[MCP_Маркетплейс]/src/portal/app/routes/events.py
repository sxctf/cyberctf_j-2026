"""SSE proxies: run transcript + exfil stream."""
import os
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

ORCH_URL  = os.environ.get("ORCH_URL",  "http://127.0.0.1:8314")
EXFIL_URL = os.environ.get("EXFIL_URL", "http://127.0.0.1:8312")

router = APIRouter(prefix="/events")


@router.get("/runs/{session_id}")
async def run_stream(session_id: str):
    async def generator() -> AsyncGenerator[str, None]:
        yield ": connected\n\n"
        try:
            async with httpx.AsyncClient(base_url=ORCH_URL, timeout=None) as client:
                async with client.stream("GET", f"/runs/{session_id}/stream") as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n\n"
        except Exception as e:
            yield f"data: {{\"type\":\"error\",\"error\":\"{e}\"}}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/exfil/{team_id}")
async def exfil_stream(team_id: str):
    async def generator() -> AsyncGenerator[str, None]:
        yield ": connected\n\n"
        try:
            async with httpx.AsyncClient(base_url=EXFIL_URL, timeout=None) as client:
                async with client.stream("GET", f"/logs/{team_id}/stream") as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n\n"
        except Exception as e:
            yield f"data: {{\"type\":\"error\",\"error\":\"{e}\"}}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/exfil/sessions")
async def exfil_stream_sessions(request: Request, sessions: str = ""):
    """Live exfil feed combined over several run session ids."""
    async def generator() -> AsyncGenerator[str, None]:
        yield ": connected\n\n"
        try:
            async with httpx.AsyncClient(base_url=EXFIL_URL, timeout=None) as client:
                async with client.stream("GET", "/logs/stream", params={"sessions": sessions}) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n\n"
        except Exception as e:
            yield f"data: {{\"type\":\"error\",\"error\":\"{e}\"}}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
