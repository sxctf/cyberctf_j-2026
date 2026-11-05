from typing import Any

from pydantic import BaseModel, Field


class DebugRequest(BaseModel):
    token: str = Field(min_length=12)
    action: str = Field(default="dump_runtime")
    parameters: dict[str, Any] = Field(default_factory=dict)


class ResetResponse(BaseModel):
    status: str
    leaked_count: int
    reset_at: str

