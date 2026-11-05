"""
Synchronous wrapper around GigaChat async client.

Uses a dedicated background thread with its own event loop so it works
in any context — plain scripts, Jupyter, FastAPI workers, etc.

Usage:
    with SyncGigaChat(verify_ssl_certs=False) as giga:
        response = giga.chat({"model": "GigaChat", "messages": [...]})
        for chunk in giga.stream({"model": "GigaChat", "messages": [...]}):
            print(chunk.choices[0].delta.content, end="")
"""

import asyncio
import queue
import threading
from typing import Any, Dict, Iterator, List, Optional, Union

from .client import GigaChat
from .models import (
    Batch,
    BatchListResponse,
    BatchResultItem,
    BalanceResponse,
    ChatPayload,
    ChatResponse,
    EmbeddingsResponse,
    FileInfo,
    FilesResponse,
    Message,
    ModelInfo,
    ModelVersionInfo,
    ModelsResponse,
    ProxyProbeResult,
    TokenUsage,
)

_SENTINEL = object()


class SyncGigaChat:
    """Synchronous GigaChat client.

    All async methods from GigaChat are exposed as regular blocking calls.
    ``astream`` becomes ``stream``, returning a plain Iterator.
    """

    def __init__(self, **kwargs):
        self._kwargs = kwargs
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="gigachat-loop"
        )
        self._thread.start()
        self._client = GigaChat(**kwargs)
        # Warm up session inside the dedicated loop
        self._run(self._client._get_session())

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._run(self._client.close())
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self, coro) -> Any:
        """Submit a coroutine to the background loop and block until done."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def _iter_async_gen(self, async_gen_coro) -> Iterator:
        """Convert an async generator into a blocking iterator via a queue."""
        q: queue.Queue = queue.Queue()

        async def _drain():
            try:
                async with async_gen_coro as gen:
                    async for item in gen:
                        q.put(item)
            except Exception as exc:
                q.put(exc)
            finally:
                q.put(_SENTINEL)

        # astream returns an async generator, not an async context manager —
        # we need a small wrapper to iterate it
        async def _drain_gen(agen):
            try:
                async for item in agen:
                    q.put(item)
            except Exception as exc:
                q.put(exc)
            finally:
                q.put(_SENTINEL)

        agen = async_gen_coro  # already the async generator object
        asyncio.run_coroutine_threadsafe(_drain_gen(agen), self._loop)

        while True:
            item = q.get()
            if item is _SENTINEL:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    # ------------------------------------------------------------------
    # Public API — mirrors GigaChat async methods
    # ------------------------------------------------------------------

    def chat(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> ChatResponse:
        return self._run(self._client.chat(
            payload, credentials=credentials, scope=scope,
            base_url=base_url, is_ift=is_ift, is_advanced=is_advanced, password=password,
        ))

    def stream(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> Iterator[ChatResponse]:
        """Blocking streaming — yields ChatResponse chunks one by one."""
        agen = self._client.astream(
            payload, credentials=credentials, scope=scope,
            base_url=base_url, is_ift=is_ift, is_advanced=is_advanced, password=password,
        )
        yield from self._iter_async_gen(agen)

    def chat_many(
        self,
        models: List[str],
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Union[ChatResponse, Exception]]:
        return self._run(self._client.chat_many(
            models, payload, credentials=credentials, scope=scope,
            is_ift=is_ift, is_advanced=is_advanced, password=password,
        ))

    def get_models(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> ModelsResponse:
        return self._run(self._client.get_models(
            credentials=credentials, scope=scope,
            base_url=base_url, is_ift=is_ift, is_advanced=is_advanced, password=password,
        ))

    def get_model(
        self,
        model_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> ModelInfo:
        return self._run(self._client.get_model(
            model_id, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def get_model_versions(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> List[ModelVersionInfo]:
        return self._run(self._client.get_model_versions(
            credentials=credentials, scope=scope,
            base_url=base_url, is_ift=is_ift, is_advanced=is_advanced, password=password,
        ))

    def get_balance(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> BalanceResponse:
        return self._run(self._client.get_balance(
            credentials=credentials, scope=scope,
            base_url=base_url, is_ift=is_ift, is_advanced=is_advanced, password=password,
        ))

    def tokens(
        self,
        model: str,
        input: Union[str, List[str]],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> List[TokenUsage]:
        return self._run(self._client.tokens(
            model, input, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def embeddings(
        self,
        model: str,
        input: Union[str, List[str]],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> EmbeddingsResponse:
        return self._run(self._client.embeddings(
            model, input, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def upload_file(
        self,
        file: Union[str, bytes],
        filename: Optional[str] = None,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> FileInfo:
        return self._run(self._client.upload_file(
            file, filename=filename, credentials=credentials,
            scope=scope, base_url=base_url,
        ))

    def get_files(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> FilesResponse:
        return self._run(self._client.get_files(
            credentials=credentials, scope=scope, base_url=base_url,
        ))

    def get_file(
        self,
        file_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> FileInfo:
        return self._run(self._client.get_file(
            file_id, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def get_file_content(
        self,
        file_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bytes:
        return self._run(self._client.get_file_content(
            file_id, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def delete_file(
        self,
        file_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bool:
        return self._run(self._client.delete_file(
            file_id, credentials=credentials, scope=scope, base_url=base_url,
        ))

    # ------------------------------------------------------------------
    # Batch API
    # ------------------------------------------------------------------

    def upload_batch_file(
        self,
        requests: List[Dict[str, Any]],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> FileInfo:
        return self._run(self._client.upload_batch_file(
            requests, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def create_batch(
        self,
        input_file_id: str,
        endpoint: str = "/v1/chat/completions",
        completion_window: str = "24h",
        metadata: Optional[Dict[str, Any]] = None,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Batch:
        return self._run(self._client.create_batch(
            input_file_id, endpoint=endpoint, completion_window=completion_window,
            metadata=metadata, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def get_batch(
        self,
        batch_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Batch:
        return self._run(self._client.get_batch(
            batch_id, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def list_batches(
        self,
        after: Optional[str] = None,
        limit: int = 20,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> BatchListResponse:
        return self._run(self._client.list_batches(
            after=after, limit=limit,
            credentials=credentials, scope=scope, base_url=base_url,
        ))

    def cancel_batch(
        self,
        batch_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Batch:
        return self._run(self._client.cancel_batch(
            batch_id, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def get_batch_results(
        self,
        batch_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> List[BatchResultItem]:
        return self._run(self._client.get_batch_results(
            batch_id, credentials=credentials, scope=scope, base_url=base_url,
        ))

    def wait_for_batch(
        self,
        batch_id: str,
        poll_interval: float = 10.0,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Batch:
        return self._run(self._client.wait_for_batch(
            batch_id, poll_interval=poll_interval,
            credentials=credentials, scope=scope, base_url=base_url,
        ))

    def tts(
        self,
        text: str,
        voice: Optional[str] = None,
        format: str = "wav",
        credentials: Optional[str] = None,
        scope: Optional[str] = "SALUTE_SPEECH_PERS",
    ) -> bytes:
        return self._run(self._client.tts(
            text, voice=voice, format=format,
            credentials=credentials, scope=scope,
        ))

    def stt(
        self,
        audio: Union[str, bytes],
        credentials: Optional[str] = None,
        scope: Optional[str] = "SALUTE_SPEECH_PERS",
    ) -> str:
        return self._run(self._client.stt(
            audio, credentials=credentials, scope=scope,
        ))
    # ------------------------------------------------------------------
    # GigaDark API - synchronous wrappers
    # ------------------------------------------------------------------

    def gigadark_query(
        self,
        messages: List[Dict[str, str]],
        client_agent_name: str = "CI00611872_CI12621384",
        model_name: str = "GigaChat-2-Pro-Dark",
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        password: Optional[str] = None,
    ) -> ChatResponse:
        """Synchronous wrapper for gigadark_query."""
        return self._run(self._client.gigadark_query(
            messages,
            client_agent_name=client_agent_name,
            model_name=model_name,
            credentials=credentials,
            scope=scope,
            base_url=base_url,
            password=password,
        ))

    # ------------------------------------------------------------------
    # Banking IFT API - synchronous wrappers
    # ------------------------------------------------------------------

    def banking_ift_chat(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        password: Optional[str] = None,
    ) -> ChatResponse:
        """Synchronous wrapper for banking_ift_chat."""
        return self._run(self._client.banking_ift_chat(
            payload,
            credentials=credentials,
            scope=scope,
            base_url=base_url,
            password=password,
        ))

    def banking_ift_stream(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Iterator[ChatResponse]:
        """Blocking streaming for Banking IFT API."""
        agen = self._client.banking_ft_stream(
            payload,
            credentials=credentials,
            scope=scope,
            base_url=base_url,
            password=password,
        )
        yield from self._iter_async_gen(agen)


    def probe_proxies(
        self,
        proxies: List[str],
        models: List[str],
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        timeout: int = 15,
    ) -> List[ProxyProbeResult]:
        return self._run(self._client.probe_proxies(
            proxies, models, payload,
            credentials=credentials, timeout=timeout,
        ))

    @property
    def concurrency_limit(self) -> Optional[int]:
        return self._client.concurrency_limit
