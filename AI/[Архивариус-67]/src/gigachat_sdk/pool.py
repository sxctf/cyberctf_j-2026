from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import aiohttp

from .client import GigaChat
from .exceptions import RateLimitError, ServerError
from .models import (
    BalanceResponse,
    ChatPayload,
    ChatResponse,
    EmbeddingsResponse,
    FileInfo,
    FilesResponse,
    ModelsResponse,
    TokenUsage,
)

logger = logging.getLogger(__name__)

# Exceptions that indicate a model is temporarily unavailable (worth retrying on next model).
# BadRequestError / AuthenticationError / ForbiddenError are NOT here — those are caller issues.
_FAILOVER_EXCEPTIONS = (RateLimitError, ServerError, aiohttp.ServerTimeoutError, asyncio.TimeoutError)


class GigaChatPool:
    """Round-robin pool of GigaChat clients — one instance per credentials key.

    Each client manages its own:
    - Bearer token (independent refresh)
    - Semaphore (auto-detected from X-RateLimit headers per key)
    - aiohttp session (independent connection pool)

    Total effective throughput = sum of per-key concurrency limits.

    Usage::

        async with GigaChatPool(
            credentials=["key_a==", "key_b==", "key_c=="],
            verify_ssl_certs=False,
        ) as pool:
            response = await pool.chat({"model": "GigaChat-2", "messages": [...]})
    """

    def __init__(self, credentials: List[str], **kwargs):
        """
        Args:
            credentials: list of Base64-encoded API keys.
            **kwargs: forwarded to every GigaChat instance
                      (scope, auth_url, base_url, verify_ssl_certs, max_concurrent, …).
        """
        if not credentials:
            raise ValueError("GigaChatPool requires at least one credentials key")
        self._clients: List[GigaChat] = [
            GigaChat(credentials=c, **kwargs) for c in credentials
        ]
        self._idx = 0
        # Cache: file path → file_id. Avoids re-uploading the same file on every request.
        self._file_cache: Dict[str, str] = {}
        self._file_cache_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Context manager                                                     #
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "GigaChatPool":
        for client in self._clients:
            await client._get_session()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def close(self) -> None:
        for client in self._clients:
            await client.close()

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _next(self) -> GigaChat:
        """Return the next client in round-robin order."""
        client = self._clients[self._idx]
        self._idx = (self._idx + 1) % len(self._clients)
        return client

    @property
    def size(self) -> int:
        """Number of keys in the pool."""
        return len(self._clients)

    # ------------------------------------------------------------------ #
    # Public API — mirrors GigaChat                                       #
    # ------------------------------------------------------------------ #

    async def chat(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        **kwargs,
    ) -> ChatResponse:
        """Send a chat request using the next available client."""
        return await self._next().chat(payload, **kwargs)

    async def chat_with_failover(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        fallback_models: List[str],
        **kwargs,
    ) -> ChatResponse:
        """Try ``payload.model`` first; on unavailability fall through ``fallback_models`` in order.

        Failover triggers on: RateLimitError, ServerError, asyncio/aiohttp TimeoutError.
        It does NOT trigger on: BadRequestError, AuthenticationError, ForbiddenError
        (those indicate a caller-side problem, not model availability).

        Each attempt still goes through the normal round-robin key selection.

        Args:
            payload: Chat payload. ``payload.model`` is the primary model.
            fallback_models: Models to try in order when the primary (and previous) fails.
            **kwargs: Forwarded to ``GigaChat.chat()``.

        Returns:
            ChatResponse — check ``resp.model`` to see which model actually answered.

        Raises:
            The last exception if every model in the list fails.

        Example::

            resp = await pool.chat_with_failover(
                payload,
                fallback_models=["GigaChat-2-Pro", "GigaChat-2"],
            )
        """
        if isinstance(payload, dict):
            payload = ChatPayload(**payload)

        primary = payload.model
        # Deduplicate while preserving order; primary goes first.
        seen: set = set()
        models_to_try: List[str] = []
        for m in [primary] + list(fallback_models):
            if m not in seen:
                seen.add(m)
                models_to_try.append(m)

        last_exc: Optional[BaseException] = None
        for model in models_to_try:
            # Build a new payload with the target model (Pydantic v1 & v2 compatible).
            try:
                p = payload.model_copy(update={"model": model})
            except AttributeError:
                p = payload.copy(update={"model": model})

            try:
                resp = await self._next().chat(p, **kwargs)
                if model != primary:
                    logger.info("chat_with_failover: used %s (primary %s was unavailable)", model, primary)
                return resp
            except _FAILOVER_EXCEPTIONS as exc:
                last_exc = exc
                logger.warning(
                    "chat_with_failover: model %s failed (%s: %s), trying next",
                    model, type(exc).__name__, exc,
                )

        raise last_exc  # type: ignore[misc]

    async def astream(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        **kwargs,
    ) -> AsyncGenerator[ChatResponse, None]:
        """Stream chat responses using the next available client."""
        async for chunk in self._next().astream(payload, **kwargs):
            yield chunk

    async def get_models(self, **kwargs) -> ModelsResponse:
        """Fetch available models (uses the first client)."""
        return await self._clients[0].get_models(**kwargs)

    async def upload_file(
        self,
        file: Union[str, bytes],
        filename: Optional[str] = None,
        use_cache: bool = True,
        skip_on_error: bool = False,
        **kwargs,
    ) -> Optional[FileInfo]:
        """Upload a file using the next available client.

        Args:
            file: Path string or raw bytes to upload.
            filename: Override filename sent to the API.
            use_cache: When *file* is a path string, cache the returned
                ``file_id`` so the same file is uploaded only once per pool
                lifetime (default ``True``).
            skip_on_error: When ``True``, any upload failure (e.g. the model
                does not support the ``/files`` endpoint, a timeout, or a
                server error) is logged as a warning and ``None`` is returned
                instead of re-raising. Callers should check for ``None`` and
                omit the attachment from the message.  Default is ``False``
                (raise on error) to preserve backwards-compatible behaviour.

        Returns:
            ``FileInfo`` on success, or ``None`` when *skip_on_error* is
            ``True`` and the upload could not be completed.
        """
        cache_key: Optional[str] = file if isinstance(file, str) and use_cache else None

        if cache_key:
            async with self._file_cache_lock:
                cached_id = self._file_cache.get(cache_key)
            if cached_id:
                return FileInfo(
                    id=cached_id,
                    object="file",
                    bytes=0,
                    created_at=0,
                    filename=filename or cache_key,
                    purpose="general",
                )

        try:
            info = await self._next().upload_file(file, filename=filename, **kwargs)
        except Exception as exc:
            if not skip_on_error:
                raise
            logger.warning(
                "upload_file skipped for %r — /files endpoint may be unavailable "
                "or unsupported by the model (%s: %s)",
                file if isinstance(file, str) else "<bytes>",
                type(exc).__name__,
                exc,
            )
            return None

        if cache_key:
            async with self._file_cache_lock:
                self._file_cache[cache_key] = info.id

        return info

    async def get_files(self, **kwargs) -> FilesResponse:
        return await self._clients[0].get_files(**kwargs)

    async def get_balance(self, **kwargs) -> BalanceResponse:
        return await self._clients[0].get_balance(**kwargs)

    async def embeddings(
        self,
        model: str,
        input: Union[str, List[str]],
        **kwargs,
    ) -> EmbeddingsResponse:
        return await self._next().embeddings(model, input, **kwargs)

    async def tokens(
        self,
        model: str,
        input: Union[str, List[str]],
        **kwargs,
    ) -> List[TokenUsage]:
        return await self._clients[0].tokens(model, input, **kwargs)
