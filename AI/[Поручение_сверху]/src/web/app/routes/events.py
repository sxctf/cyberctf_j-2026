"""SSE proxy: forwards webhook service events to the browser."""
import asyncio
import json
import os
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..auth_middleware import get_optional_team

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://task05-webhook:8000")
router = APIRouter(prefix="/events")


@router.get("/activity")
async def activity_stream(team=Depends(get_optional_team)):
    """Proxy SSE from webhook service, filtered by team's issues."""
    async def generator() -> AsyncGenerator[str, None]:
        yield ": connected\n\n"
        async with httpx.AsyncClient(base_url=WEBHOOK_URL, timeout=None) as client:
            async with client.stream("GET", "/events") as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        yield line + "\n\n"
                    elif line.startswith(":"):
                        yield line + "\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
