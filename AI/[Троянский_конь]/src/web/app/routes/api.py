"""API routes: upload, job status, DNS proxy."""
import json
import os
import uuid
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_middleware import get_optional_team, get_required_team
from ..core.jobs import Job, JobStatus, SessionLocal, get_session, sha256_bytes
from ..core.worker import enqueue

router = APIRouter(prefix="/api")

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/uploads"))
DNS_LOGGER_URL = os.environ.get("DNS_LOGGER_URL", "http://127.0.0.1:8053")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".pt", ".bin", ".pth", ".pkl"}


@router.post("/upload")
async def upload_file(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    session: Annotated[AsyncSession, Depends(get_session)],
    team=Depends(get_required_team),
):
    # Validate extension
    filename = file.filename or "upload.pt"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, detail=f"Extension {ext} not allowed. Use: {', '.join(ALLOWED_EXTENSIONS)}")

    # Read with size limit
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail="File too large (max 50 MB)")

    file_hash = sha256_bytes(content)

    # Save to upload dir
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{job_id}{ext}"
    save_path.write_bytes(content)

    # Create job record
    job = Job(
        id=job_id,
        team_id=str(team.team_id),
        filename=filename,
        file_size=len(content),
        file_sha256=file_hash,
        status=JobStatus.QUEUED,
    )
    session.add(job)
    await session.commit()

    # Enqueue for processing
    await enqueue(job_id, str(save_path))

    return {
        "job_id": job_id,
        "filename": filename,
        "size": len(content),
        "sha256": file_hash,
    }


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    team=Depends(get_required_team),
):
    result = await session.execute(
        select(Job).where(Job.id == job_id, Job.team_id == str(team.team_id))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404)
    return _job_to_dict(job)


@router.get("/dns/queries")
async def dns_queries(since_ts: str = "", team=Depends(get_optional_team)):
    """Proxy DNS query log from dns-logger service."""
    try:
        async with httpx.AsyncClient(base_url=DNS_LOGGER_URL, timeout=5.0) as client:
            params = {"limit": 100}
            if since_ts:
                params["since_ts"] = since_ts
            resp = await client.get("/queries", params=params)
            return resp.json()
    except Exception as e:
        return []


def _job_to_dict(job: Job) -> dict:
    exfil = []
    try:
        exfil = json.loads(job.exfil_data) if job.exfil_data else []
    except Exception:
        pass
    return {
        "id": job.id,
        "filename": job.filename,
        "file_size": job.file_size,
        "sha256": job.file_sha256,
        "status": job.status,
        "scan_verdict": job.scan_verdict,
        "scan_detail": job.scan_detail,
        "loader_stdout": job.loader_stdout,
        "loader_stderr": job.loader_stderr,
        "loader_returncode": job.loader_returncode,
        "exfil": exfil,
        "dns_activity": job.dns_activity,
        "timed_out": job.timed_out,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
