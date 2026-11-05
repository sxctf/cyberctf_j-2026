"""Job queue and state management for task03 uploads."""
import asyncio
import hashlib
import os
import uuid
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import String, Text, DateTime, Boolean, Integer
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DB_PATH = os.environ.get("TASK03_DB_PATH", "/data/task03.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class JobStatus(str, Enum):
    QUEUED = "queued"
    SCANNING = "scanning"
    SCAN_BLOCKED = "scan_blocked"
    LOADING = "loading"
    DONE = "done"
    ERROR = "error"
    TIMEOUT = "timeout"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED)
    scan_verdict: Mapped[str] = mapped_column(String(16), default="")   # clean / blocked
    scan_detail: Mapped[str] = mapped_column(Text, default="")
    loader_stdout: Mapped[str] = mapped_column(Text, default="")
    loader_stderr: Mapped[str] = mapped_column(Text, default="")
    loader_returncode: Mapped[int] = mapped_column(Integer, default=0)
    exfil_data: Mapped[str] = mapped_column(Text, default="")          # JSON list
    dns_activity: Mapped[bool] = mapped_column(Boolean, default=False)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


async def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with SessionLocal() as s:
        yield s


# In-memory event bus for SSE: job_id -> list of pending events
_event_queues: dict[str, asyncio.Queue] = {}


def get_event_queue(job_id: str) -> asyncio.Queue:
    if job_id not in _event_queues:
        _event_queues[job_id] = asyncio.Queue()
    return _event_queues[job_id]


async def push_event(job_id: str, event: dict):
    q = get_event_queue(job_id)
    await q.put(event)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
