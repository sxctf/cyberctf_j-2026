from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field

class FunctionCall(BaseModel):
    name: str
    arguments: Dict[str, Any]

class Message(BaseModel):
    role: str
    content: str
    reasoning_content: Optional[str] = None
    name: Optional[str] = None
    function_call: Optional[FunctionCall] = None
    attachments: Optional[List[str]] = None
    data: Optional[Any] = None
    functions: Optional[List[Dict[str, Any]]] = None

class Delta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    function_call: Optional[FunctionCall] = None

class ChatPayload(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    max_tokens: Optional[int] = None
    repetition_penalty: Optional[float] = 1.0
    update_interval: Optional[float] = None
    functions: Optional[List[Dict[str, Any]]] = None
    function_call: Optional[Union[str, Dict[str, str]]] = None

class Choice(BaseModel):
    message: Optional[Message] = None
    delta: Optional[Delta] = None
    index: int
    finish_reason: Optional[str] = None

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatResponse(BaseModel):
    choices: List[Choice]
    created: int
    model: str
    usage: Optional[Usage] = None
    object: str = "chat.completion"

class TokenUsage(BaseModel):
    tokens: int
    characters: int

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: Optional[int] = None
    owned_by: Optional[str] = None
    version: Optional[str] = None

    model_config = {"extra": "allow"}


class ModelsResponse(BaseModel):
    data: List[ModelInfo]
    object: str = "list"


@dataclass
class ModelVersionInfo:
    """Specific deployed version of a model, discovered via a minimal chat probe."""
    model_id: str
    version: str

    def __str__(self) -> str:
        return f"{self.model_id} → {self.version}"

class BalanceResponse(BaseModel):
    balance: float
    unit: str

class Embedding(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int

class EmbeddingsUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

class EmbeddingsResponse(BaseModel):
    object: str = "list"
    data: List[Embedding]
    model: str
    usage: Optional[EmbeddingsUsage] = None

class FileInfo(BaseModel):
    id: str
    object: str = "file"
    bytes: int
    created_at: int
    filename: str
    purpose: str

class FilesResponse(BaseModel):
    data: List[FileInfo]
    object: str = "list"


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------

class BatchRequestCounts(BaseModel):
    total: int = 0
    completed: int = 0
    failed: int = 0


class Batch(BaseModel):
    id: str
    object: str = "batch"
    endpoint: str
    status: str  # validating | in_progress | finalizing | completed | failed | expired | cancelling | cancelled
    input_file_id: str
    output_file_id: Optional[str] = None
    error_file_id: Optional[str] = None
    completion_window: str = "24h"
    created_at: Optional[int] = None
    in_progress_at: Optional[int] = None
    expires_at: Optional[int] = None
    finalizing_at: Optional[int] = None
    completed_at: Optional[int] = None
    failed_at: Optional[int] = None
    expired_at: Optional[int] = None
    cancelling_at: Optional[int] = None
    cancelled_at: Optional[int] = None
    request_counts: Optional[BatchRequestCounts] = None
    metadata: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}

    @property
    def is_done(self) -> bool:
        return self.status in ("completed", "failed", "expired", "cancelled")

    @property
    def is_success(self) -> bool:
        return self.status == "completed"


class BatchListResponse(BaseModel):
    data: List[Batch]
    object: str = "list"
    first_id: Optional[str] = None
    last_id: Optional[str] = None
    has_more: bool = False


class BatchResultItem(BaseModel):
    """Single line from the output JSONL file."""
    id: str
    custom_id: str
    response: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}

    def get_chat_response(self) -> Optional["ChatResponse"]:
        """Parse response body into ChatResponse if available."""
        if self.response and self.response.get("status_code") == 200:
            body = self.response.get("body") or {}
            try:
                return ChatResponse(**body)
            except Exception:
                return None
        return None


@dataclass
class ProxyProbeResult:
    proxy: str
    model: str
    success: bool
    latency_ms: float
    error: Optional[str] = None
    response: Optional["ChatResponse"] = field(default=None, repr=False)

    def __str__(self) -> str:
        status = "OK" if self.success else "FAIL"
        detail = f"{self.latency_ms:.0f}ms" if self.success else self.error
        return f"[{status}] {self.proxy} × {self.model} — {detail}"
