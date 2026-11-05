"""SSE: poll run status and stream new screenshots/transcript entries."""
import asyncio
import json
import os
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

ORCH_URL = os.environ.get("ORCH_URL", "http://task06-orchestrator:8022")
router = APIRouter(prefix="/events")


@router.get("/runs/{session_id}")
async def run_stream(session_id: str):
    """Poll orchestrator every 2s, stream new transcript entries and screenshots."""
    async def generator() -> AsyncGenerator[str, None]:
        yield ": connected\n\n"
        sent_count = 0
        sent_screenshots = 0

        async with httpx.AsyncClient(base_url=ORCH_URL, timeout=10) as client:
            for _ in range(150):  # max 5 min @ 2s polls
                await asyncio.sleep(2)
                yield ": heartbeat\n\n"  # keep connection alive through proxies
                try:
                    r = await client.get(f"/runs/{session_id}")
                    if r.status_code != 200:
                        continue
                    data = r.json()
                except Exception:
                    continue

                transcript = data.get("transcript", [])
                screenshots = data.get("screenshots", [])

                # Stream new transcript entries
                for entry in transcript[sent_count:]:
                    yield f"data: {json.dumps({'type': 'entry', 'entry': entry})}\n\n"
                    sent_count = len(transcript)

                # Stream new screenshots
                for ss in screenshots[sent_screenshots:]:
                    yield f"data: {json.dumps({'type': 'screenshot', 'data': ss})}\n\n"
                    sent_screenshots = len(screenshots)

                # Stream status updates
                if data["status"] in ("completed", "error"):
                    yield f"data: {json.dumps({'type': 'done', 'run': data})}\n\n"
                    break
                else:
                    yield f"data: {json.dumps({'type': 'status', 'status': data['status']})}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
