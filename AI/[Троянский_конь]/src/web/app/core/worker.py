"""Background worker: processes upload jobs through scanner → loader pipeline."""
import asyncio
import json
import os
from datetime import datetime, UTC
from pathlib import Path

import httpx
from sqlalchemy import select

from .jobs import Job, JobStatus, SessionLocal, push_event, sha256_bytes
from .scanner import run_picklescan

SANDBOX_URL = os.environ.get("SANDBOX_URL", "http://127.0.0.1:8102")
DNS_LOGGER_URL = os.environ.get("DNS_LOGGER_URL", "http://127.0.0.1:8053")
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/uploads"))

# Global FIFO queue
_job_queue: asyncio.Queue = asyncio.Queue()


async def enqueue(job_id: str, file_path: str):
    await _job_queue.put((job_id, file_path))


async def run_worker():
    """Long-running coroutine that processes jobs from the queue."""
    while True:
        job_id, file_path = await _job_queue.get()
        try:
            await _process_job(job_id, file_path)
        except Exception as e:
            await _update_job(job_id, status=JobStatus.ERROR, scan_detail=str(e))
            await push_event(job_id, {"step": "error", "msg": str(e)})
        finally:
            _job_queue.task_done()


async def _process_job(job_id: str, file_path: str):
    # ---- Step 1: File received ----
    await push_event(job_id, {"step": "received", "msg": "File received, queued for scanning"})

    # ---- Step 2: Picklescan ----
    await _update_job(job_id, status=JobStatus.SCANNING)
    await push_event(job_id, {"step": "scanning", "msg": "Running picklescan 0.0.30..."})

    verdict, detail = await run_picklescan(file_path)

    if verdict == "blocked":
        await _update_job(
            job_id,
            status=JobStatus.SCAN_BLOCKED,
            scan_verdict="blocked",
            scan_detail=detail,
            completed_at=datetime.now(UTC),
        )
        await push_event(job_id, {
            "step": "scan_blocked",
            "msg": f"Picklescan blocked the file",
            "detail": detail,
        })
        return

    # Clean
    await _update_job(job_id, scan_verdict="clean", scan_detail=detail)
    await push_event(job_id, {"step": "scan_clean", "msg": "Scan passed — loading in sandbox..."})

    # ---- Step 3: Sandbox load ----
    await _update_job(job_id, status=JobStatus.LOADING)
    await push_event(job_id, {"step": "loading", "msg": "Executing in isolated sandbox..."})

    # Record DNS baseline before run
    dns_before = await _get_dns_queries()

    loader_result = await _call_sandbox(job_id, file_path)

    # Check DNS activity after run
    dns_after = await _get_dns_queries()
    new_dns = [q for q in dns_after if q not in dns_before]
    dns_active = len(new_dns) > 0

    # ---- Step 4: Result ----
    final_status = JobStatus.DONE
    if loader_result.get("timed_out"):
        final_status = JobStatus.TIMEOUT

    await _update_job(
        job_id,
        status=final_status,
        loader_stdout=loader_result.get("stdout", ""),
        loader_stderr=loader_result.get("stderr", ""),
        loader_returncode=loader_result.get("returncode", 0),
        exfil_data=json.dumps(loader_result.get("exfil", [])),
        dns_activity=dns_active,
        completed_at=datetime.now(UTC),
    )

    exfil = loader_result.get("exfil", [])
    msg = "Load complete."
    if exfil:
        msg += f" {len(exfil)} file(s) found in exfil dir."
    if dns_active:
        msg += f" DNS activity detected ({len(new_dns)} queries)."
    if loader_result.get("timed_out"):
        msg = "Load timed out after 30s."

    await push_event(job_id, {
        "step": "done",
        "msg": msg,
        "stdout_preview": loader_result.get("stdout", "")[:300],
        "exfil_count": len(exfil),
        "dns_active": dns_active,
    })

    # Cleanup file
    try:
        Path(file_path).unlink()
    except Exception:
        pass


async def _call_sandbox(job_id: str, file_path: str) -> dict:
    """Send file to sandbox service for pickle.load() execution."""
    try:
        async with httpx.AsyncClient(base_url=SANDBOX_URL, timeout=45.0) as client:
            with open(file_path, "rb") as f:
                content = f.read()
            filename = Path(file_path).name
            resp = await client.post(
                "/load",
                data={"job_id": job_id},
                files={"file": (filename, content, "application/octet-stream")},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1, "exfil": [], "timed_out": False}


async def _get_dns_queries() -> list:
    """Fetch recent DNS queries from logger."""
    try:
        async with httpx.AsyncClient(base_url=DNS_LOGGER_URL, timeout=3.0) as client:
            resp = await client.get("/queries", params={"limit": 200})
            return resp.json()
    except Exception:
        return []


async def _update_job(job_id: str, **kwargs):
    async with SessionLocal() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)
            await session.commit()
