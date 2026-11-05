import asyncio
import json
import logging
import ssl
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .auth import TokenManager
from .exceptions import (
    BadRequestError,
    ForbiddenError,
    GigaChatException,
    NotFoundError,
    RateLimitError,
    ServerError,
    AuthenticationError
)
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
    TokenUsage
)

logger = logging.getLogger(__name__)

def _api_retry():
    """Retry decorator for transient API errors (429, 5xx)."""
    return retry(
        retry=retry_if_exception_type((RateLimitError, ServerError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )

class GigaChat:
    """
    Standalone GigaChat SDK.
    Supports multiple credentials, scopes, and domains.
    """

    DEFAULT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    DEFAULT_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1"

    SPEECH_BASE_URL = "https://smartspeech.sber.ru/rest/v1"

    IFT_AUTH_URL = "https://gigachat.sberdevices.ru/v1/token"
    IFT_BASE_URL = "https://gigachat.ift.sberdevices.ru/v1"

    ADVANCED_AUTH_URL = "https://gigachat.sberdevices.ru/v1/token"
    ADVANCED_BASE_URL = "https://gigachat.sberdevices.ru/v1"

    # GigaDark API endpoint (agent API for GigaChat-2-Pro-Dark)
    GIGADARK_BASE_URL = "https://cspkitaicore.ift-23-24-mlb.ocp-geo.ocp.delta.sbrf.ru/agent-api/v1"

    # Banking IFT API endpoint
    BANKING_IFT_BASE_URL = "https://ift-giga.sberdevices.ru/v1"

    def __init__(
        self,
        credentials: Optional[str] = None,
        scope: str = "GIGACHAT_API_PERS",
        base_url: str = DEFAULT_BASE_URL,
        auth_url: str = DEFAULT_AUTH_URL,
        verify_ssl_certs: bool = True,
        ca_bundle: Optional[str] = None,
        is_ift: bool = False,
        is_advanced: bool = False,
        password: Optional[str] = None,
        timeout: int = 30,
        upload_timeout: int = 15,
        verbose: bool = False,
        max_concurrent: Optional[int] = None,
        proxy: Optional[str] = None,
        ssl_cert: Optional[str] = None,
        ssl_key: Optional[str] = None,
    ):
        self.credentials = credentials
        self.scope = scope
        self.base_url = base_url
        self.auth_url = auth_url
        self.verify_ssl_certs = verify_ssl_certs
        self.is_ift = is_ift
        self.is_advanced = is_advanced
        self.password = password
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.upload_timeout = aiohttp.ClientTimeout(total=upload_timeout)
        self.verbose = verbose
        self._max_concurrent = max_concurrent  # None = auto-detect on first use
        self._concurrency_target: Optional[int] = max_concurrent  # tracks current live limit

        self.proxy = proxy
        self.ssl_cert = ssl_cert
        self.ssl_key = ssl_key
        self._token_manager = TokenManager()
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._semaphore_lock = asyncio.Lock()
        self._scope_override: Optional[str] = None  # set after auto-detect
        self._reprobe_task: Optional[asyncio.Task] = None

        if verify_ssl_certs:
            if ca_bundle:
                self._ssl_context = ssl.create_default_context(cafile=ca_bundle)
            elif ssl_cert and ssl_key:
                self._ssl_context = ssl.create_default_context()
                self._ssl_context.load_cert_chain(certfile=ssl_cert, keyfile=ssl_key)
                if ssl_cert:
                    self._ssl_context.load_verify_locations(cafile=ssl_cert)
            else:
                self._ssl_context = True
        else:
            self._ssl_context = False

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _make_trace_config(self) -> aiohttp.TraceConfig:
        trace = aiohttp.TraceConfig()

        async def on_start(session, ctx, params):
            ctx.start = time.monotonic()

        async def on_end(session, ctx, params):
            elapsed = (time.monotonic() - ctx.start) * 1000
            log = logger.debug if not self.verbose else logger.info
            log(
                "%s %s → %d (%.0f ms)",
                params.method,
                str(params.url).split("?")[0],
                params.response.status,
                elapsed,
            )

        async def on_exception(session, ctx, params):
            elapsed = (time.monotonic() - ctx.start) * 1000
            logger.warning(
                "%s %s → ERROR %s (%.0f ms)",
                params.method,
                str(params.url).split("?")[0],
                type(params.exception).__name__,
                elapsed,
            )

        trace.on_request_start.append(on_start)
        trace.on_request_end.append(on_end)
        trace.on_request_exception.append(on_exception)
        return trace

    def _make_connector(self):
        if self.proxy and self.proxy.startswith(("socks4://", "socks4a://", "socks5://", "socks5h://")):
            try:
                from aiohttp_socks import ProxyConnector
            except ImportError:
                raise ImportError(
                    "SOCKS proxy support requires 'aiohttp-socks'. "
                    "Install it with: pip install gigachat-sdk-lite[socks]"
                )
            return ProxyConnector.from_url(
                self.proxy,
                limit=20,
                limit_per_host=10,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
                ssl=self._ssl_context if self._ssl_context is not True else None,
            )
        return aiohttp.TCPConnector(
            limit=20,
            limit_per_host=10,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            kwargs = dict(
                timeout=self.timeout,
                connector=self._make_connector(),
                trace_configs=[self._make_trace_config()],
            )
            if self.proxy and not self.proxy.startswith(
                ("socks4://", "socks4a://", "socks5://", "socks5h://")
            ):
                kwargs["proxy"] = self.proxy
            self._session = aiohttp.ClientSession(**kwargs)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _detect_concurrency(self) -> int:
        """Probe /models endpoint to read X-RateLimit headers and determine concurrency."""
        try:
            token = await self._get_token()
            url = f"{self.base_url}/models"
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            session = await self._get_session()
            async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
                # GigaChat may return X-RateLimit-Limit-Requests or similar
                for header in ("X-RateLimit-Limit-Requests", "X-RateLimit-Requests-Limit",
                               "X-Ratelimit-Limit", "RateLimit-Limit"):
                    value = resp.headers.get(header)
                    if value and value.isdigit():
                        detected = max(1, int(value))
                        logger.info("Auto-detected concurrency limit: %d (from %s)", detected, header)
                        return detected
        except Exception as e:
            logger.debug("Concurrency probe failed: %s", e)

        # Conservative default: 2 for free tier (PERS), 5 for corp
        default = 2 if "PERS" in self.scope else 5
        logger.info("Using default concurrency limit: %d", default)
        return default

    async def _get_semaphore(self) -> asyncio.Semaphore:
        """Return the concurrency semaphore, initialising it once (with auto-detect if needed)."""
        if self._semaphore is not None:
            return self._semaphore
        async with self._semaphore_lock:
            if self._semaphore is None:
                limit = self._max_concurrent or await self._detect_concurrency()
                self._concurrency_target = limit
                self._semaphore = asyncio.Semaphore(limit)
                logger.debug("Semaphore created with limit=%d", limit)
        return self._semaphore

    async def _on_rate_limit(self) -> None:
        """Shrink semaphore by 1 on 429 and schedule a re-probe after 60 s."""
        if self._semaphore is None:
            return
        async with self._semaphore_lock:
            current = self._concurrency_target or 1
            new_target = max(1, current - 1)
            if new_target < current:
                # Steal one available slot so the change takes effect immediately.
                if self._semaphore._value > 0:  # noqa: SLF001
                    self._semaphore._value -= 1  # noqa: SLF001
                self._concurrency_target = new_target
                logger.info("Rate limit hit: concurrency reduced %d → %d", current, new_target)

            # Schedule a re-probe (only one at a time).
            if self._reprobe_task is None or self._reprobe_task.done():
                self._reprobe_task = asyncio.get_running_loop().create_task(
                    self._schedule_reprobe(60.0)
                )

    async def _schedule_reprobe(self, delay: float) -> None:
        """Wait *delay* seconds then re-probe the rate-limit headers and restore concurrency."""
        await asyncio.sleep(delay)
        try:
            new_limit = await self._detect_concurrency()
        except Exception as exc:
            logger.debug("Concurrency re-probe failed: %s", exc)
            return
        async with self._semaphore_lock:
            if self._semaphore is None:
                return
            current = self._concurrency_target or 1
            if new_limit > current:
                # Release stolen slots back into the semaphore.
                for _ in range(new_limit - current):
                    self._semaphore.release()
                self._concurrency_target = new_limit
                logger.info("Concurrency re-probe: restored %d → %d", current, new_limit)
            else:
                logger.debug("Concurrency re-probe: limit still %d (no change)", new_limit)

    @property
    def concurrency_limit(self) -> Optional[int]:
        """Current concurrency limit (None if not yet initialised)."""
        if self._semaphore is not None:
            return self._semaphore._value  # noqa: SLF001 — internal asyncio attribute
        return self._max_concurrent

    _SCOPE_FALLBACKS = {
        "GIGACHAT_API_CORP": "GIGACHAT_API_PERS",
        "GIGACHAT_API_B2B":  "GIGACHAT_API_PERS",
    }

    def _resolve_contour(
        self,
        is_ift: Optional[bool],
        is_advanced: Optional[bool],
    ) -> tuple:
        """Return (auth_url, base_url, use_password_auth) for a given contour."""
        eff_ift = is_ift if is_ift is not None else self.is_ift
        eff_adv = is_advanced if is_advanced is not None else self.is_advanced
        if eff_adv:
            return self.ADVANCED_AUTH_URL, self.ADVANCED_BASE_URL, True
        if eff_ift:
            return self.IFT_AUTH_URL, self.IFT_BASE_URL, True
        return None, None, False

    async def _get_token(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        auth_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        password: Optional[str] = None
    ) -> str:
        session = await self._get_session()
        # Explicit scope from caller → use as-is, no auto-detect
        effective_scope = scope or self._scope_override or self.scope
        try:
            return await self._token_manager.get_token(
                session=session,
                credentials=credentials or self.credentials,
                scope=effective_scope,
                auth_url=auth_url or self.auth_url,
                ssl_context=self._ssl_context,
                is_ift=is_ift if is_ift is not None else self.is_ift,
                password=password or self.password,
            )
        except AuthenticationError:
            # Only auto-fallback when scope wasn't explicitly specified by the caller
            if scope is not None or is_ift:
                raise
            alt_scope = self._SCOPE_FALLBACKS.get(effective_scope)
            if alt_scope is None:
                raise
            logger.info(
                "Scope %s rejected by auth server, retrying with %s",
                effective_scope, alt_scope,
            )
            token = await self._token_manager.get_token(
                session=session,
                credentials=credentials or self.credentials,
                scope=alt_scope,
                auth_url=auth_url or self.auth_url,
                ssl_context=self._ssl_context,
                is_ift=False,
                password=password or self.password,
            )
            # Cache the working scope so all subsequent calls use it directly
            self._scope_override = alt_scope
            self.scope = alt_scope
            logger.info("Scope auto-detected: %s (saved as default)", alt_scope)
            return token

    async def _handle_response(self, resp: aiohttp.ClientResponse):
        if resp.status == 200:
            return

        text = await resp.text()
        try:
            data = json.loads(text)
            message = data.get("message", text)
        except:
            message = text

        if resp.status == 400:
            raise BadRequestError(message, status_code=400, response_text=text)
        elif resp.status == 401:
            raise AuthenticationError(message, status_code=401, response_text=text)
        elif resp.status == 403:
            raise ForbiddenError(message, status_code=403, response_text=text)
        elif resp.status == 404:
            raise NotFoundError(message, status_code=404, response_text=text)
        elif resp.status == 429:
            await self._on_rate_limit()
            raise RateLimitError(message, status_code=429, response_text=text)
        elif resp.status >= 500:
            raise ServerError(message, status_code=resp.status, response_text=text)
        else:
            raise GigaChatException(f"Unknown error: {resp.status} - {message}", status_code=resp.status, response_text=text)

    @_api_retry()
    async def chat(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat request."""
        if isinstance(payload, dict):
            payload = ChatPayload(**payload)

        c_auth_url, c_base_url, use_pw = self._resolve_contour(is_ift, is_advanced)
        token = await self._get_token(
            credentials=credentials,
            scope=scope,
            is_ift=use_pw,
            password=password,
            auth_url=c_auth_url,
        )
        url = f"{base_url or c_base_url or self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        sem = await self._get_semaphore()
        async with sem:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload.dict(exclude_none=True), ssl=self._ssl_context) as resp:
                await self._handle_response(resp)
                data = await resp.json()
                return ChatResponse(**data)

    async def chat_many(
        self,
        models: List[str],
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Union[ChatResponse, Exception]]:
        """Run the same payload on multiple models concurrently.

        Returns a dict {model_id: ChatResponse | Exception}.
        Exceptions are captured per-model so one failure doesn't cancel others.
        """
        if isinstance(payload, dict):
            payload = ChatPayload(**payload)

        async def _run(model: str) -> tuple:
            p = payload.copy()
            p.model = model
            try:
                return model, await self.chat(p, credentials=credentials, scope=scope,
                                              is_ift=is_ift, is_advanced=is_advanced,
                                              password=password)
            except Exception as exc:
                return model, exc

        results = await asyncio.gather(*(_run(m) for m in models))
        return dict(results)

    async def probe_proxies(
        self,
        proxies: List[str],
        models: List[str],
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        timeout: int = 15,
    ) -> List[ProxyProbeResult]:
        """Test every proxy × model combination concurrently.

        Creates a temporary GigaChat client per proxy (inherits SSL/scope/
        credentials from self), fires a chat request for each model, and
        collects latency + success/error info.

        Returns a flat list of ProxyProbeResult sorted by (proxy, model).
        """
        if isinstance(payload, dict):
            payload = ChatPayload(**payload)

        async def _probe(proxy: str, model: str) -> ProxyProbeResult:
            p = payload.copy()
            p.model = model
            start = time.monotonic()
            try:
                client = GigaChat(
                    credentials=credentials or self.credentials,
                    scope=self._scope_override or self.scope,
                    auth_url=self.auth_url,
                    verify_ssl_certs=self.verify_ssl_certs,
                    timeout=timeout,
                    proxy=proxy,
                    verbose=False,
                )
                async with client:
                    response = await client.chat(p)
                latency = (time.monotonic() - start) * 1000
                return ProxyProbeResult(
                    proxy=proxy, model=model, success=True,
                    latency_ms=latency, response=response,
                )
            except Exception as exc:
                latency = (time.monotonic() - start) * 1000
                return ProxyProbeResult(
                    proxy=proxy, model=model, success=False,
                    latency_ms=latency, error=f"{type(exc).__name__}: {exc}",
                )

        combos = [(proxy, model) for proxy in proxies for model in models]
        results = await asyncio.gather(*(_probe(p, m) for p, m in combos))
        return sorted(results, key=lambda r: (r.proxy, r.model))

    async def astream(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> AsyncGenerator[ChatResponse, None]:
        """Stream chat responses."""
        if isinstance(payload, dict):
            payload = ChatPayload(**payload)
        payload.stream = True

        c_auth_url, c_base_url, use_pw = self._resolve_contour(is_ift, is_advanced)
        token = await self._get_token(
            credentials=credentials, scope=scope, is_ift=use_pw, password=password,
            auth_url=c_auth_url,
        )
        url = f"{base_url or c_base_url or self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        sem = await self._get_semaphore()
        async with sem:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload.dict(exclude_none=True), ssl=self._ssl_context) as resp:
                await self._handle_response(resp)
                buffer = ""
                async for chunk in resp.content.iter_any():
                    buffer += chunk.decode("utf-8")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        try:
                            yield ChatResponse(**json.loads(data_str))
                        except json.JSONDecodeError:
                            logger.warning("SSE parse error, skipping chunk: %.100s", data_str)

    @_api_retry()
    async def get_models(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> ModelsResponse:
        """Get available models."""
        c_auth_url, c_base_url, use_pw = self._resolve_contour(is_ift, is_advanced)
        token = await self._get_token(
            credentials=credentials, scope=scope, is_ift=use_pw, password=password,
            auth_url=c_auth_url,
        )
        url = f"{base_url or c_base_url or self.base_url}/models"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        session = await self._get_session()
        async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            data = await resp.json()
            return ModelsResponse(**data)

    async def get_model(
        self,
        model_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> ModelInfo:
        """Get information about a specific model."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/models/{model_id}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        session = await self._get_session()
        async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            data = await resp.json()
            return ModelInfo(**data)

    async def get_model_versions(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> List[ModelVersionInfo]:
        """Return the specific deployed version string for every available model.

        GigaChat's /models endpoint returns only logical model IDs (e.g. "GigaChat",
        "GigaChat-Pro").  The concrete revision (e.g. "GigaChat:3.1.25.3") is
        visible only in the ``model`` field of a chat completion response.
        This method fires a minimal 1-token chat probe per model concurrently and
        collects the version strings reported by the server.

        Models that fail the probe are skipped (logged at WARNING level).
        """
        models_resp = await self.get_models(
            credentials=credentials, scope=scope,
            base_url=base_url, is_ift=is_ift, is_advanced=is_advanced, password=password,
        )

        probe_payload_base = {
            "messages": [{"role": "user", "content": "1"}],
            "max_tokens": 1,
            "temperature": 0.0,
        }

        async def _probe(model_id: str) -> Optional[ModelVersionInfo]:
            payload = ChatPayload(**{**probe_payload_base, "model": model_id})
            try:
                resp = await self.chat(
                    payload,
                    credentials=credentials, scope=scope,
                    base_url=base_url, is_ift=is_ift, is_advanced=is_advanced,
                    password=password,
                )
                return ModelVersionInfo(model_id=model_id, version=resp.model)
            except Exception as exc:
                logger.debug("Version probe skipped for model %r: %s", model_id, exc)
                return None

        results = await asyncio.gather(*(_probe(m.id) for m in models_resp.data))
        return [r for r in results if r is not None]

    @_api_retry()
    async def get_balance(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        is_ift: Optional[bool] = None,
        is_advanced: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> BalanceResponse:
        """Get account balance."""
        c_auth_url, c_base_url, use_pw = self._resolve_contour(is_ift, is_advanced)
        token = await self._get_token(
            credentials=credentials, scope=scope, is_ift=use_pw, password=password,
            auth_url=c_auth_url,
        )
        url = f"{base_url or c_base_url or self.base_url}/balance"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        session = await self._get_session()
        async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            data = await resp.json()
            return BalanceResponse(**data)

    async def tokens(
        self,
        model: str,
        input: Union[str, List[str]],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> List[TokenUsage]:
        """Count tokens in input."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/tokens/count"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "model": model,
            "input": [input] if isinstance(input, str) else input
        }

        session = await self._get_session()
        async with session.post(url, headers=headers, json=payload, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            data = await resp.json()
            return [TokenUsage(**item) for item in data]

    @_api_retry()
    async def embeddings(
        self,
        model: str,
        input: Union[str, List[str]],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> EmbeddingsResponse:
        """Generate embeddings for the given input."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/embeddings"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "model": model,
            "input": [input] if isinstance(input, str) else input
        }

        session = await self._get_session()
        async with session.post(url, headers=headers, json=payload, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            data = await resp.json()
            return EmbeddingsResponse(**data)

    async def upload_file(
        self,
        file: Union[str, bytes],
        filename: Optional[str] = None,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> FileInfo:
        """Upload a file."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/files"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        data = aiohttp.FormData()
        if isinstance(file, str):
            import os
            filename = filename or os.path.basename(file)
            with open(file, "rb") as f:
                content = f.read()
        else:
            content = file
            filename = filename or "file"

        data.add_field("file", content, filename=filename)
        data.add_field("purpose", "general")

        session = await self._get_session()
        async with session.post(
            url, headers=headers, data=data, ssl=self._ssl_context,
            timeout=self.upload_timeout,
        ) as resp:
            await self._handle_response(resp)
            result = await resp.json()
            return FileInfo(**result)

    async def get_files(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> FilesResponse:
        """List uploaded files."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/files"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        session = await self._get_session()
        async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            data = await resp.json()
            return FilesResponse(**data)

    async def get_file(
        self,
        file_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> FileInfo:
        """Get information about a specific file."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/files/{file_id}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        session = await self._get_session()
        async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            data = await resp.json()
            return FileInfo(**data)

    async def get_file_content(
        self,
        file_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bytes:
        """Download a file's content."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/files/{file_id}/content"

        headers = {
            "Authorization": f"Bearer {token}",
        }

        session = await self._get_session()
        async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            return await resp.read()

    async def delete_file(
        self,
        file_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bool:
        """Delete a file."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/files/{file_id}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        session = await self._get_session()
        async with session.delete(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            return resp.status == 200

    # ------------------------------------------------------------------
    # Batch API
    # ------------------------------------------------------------------

    async def upload_batch_file(
        self,
        requests: List[Dict[str, Any]],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> FileInfo:
        """Serialize *requests* to JSONL and upload as a batch input file.

        Each item in *requests* must be a dict with keys:
            custom_id  – unique string ID you assign (echoed back in results)
            method     – HTTP method, e.g. "POST"
            url        – endpoint path, e.g. "/v1/chat/completions"
            body       – the request body dict (model, messages, …)

        Returns the FileInfo of the uploaded file (use .id as input_file_id).
        """
        lines = [json.dumps(r, ensure_ascii=False) for r in requests]
        content = "\n".join(lines).encode("utf-8")

        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/files"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        data = aiohttp.FormData()
        data.add_field(
            "file",
            content,
            filename="batch_input.jsonl",
            content_type="text/plain",
        )
        data.add_field("purpose", "general")

        session = await self._get_session()
        async with session.post(
            url, headers=headers, data=data,
            ssl=self._ssl_context, timeout=self.upload_timeout,
        ) as resp:
            await self._handle_response(resp)
            return FileInfo(**(await resp.json()))

    @_api_retry()
    async def create_batch(
        self,
        input_file_id: str,
        endpoint: str = "/v1/chat/completions",
        completion_window: str = "24h",
        metadata: Optional[Dict[str, Any]] = None,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Batch:
        """Create a batch job.

        Args:
            input_file_id:     ID of the JSONL file uploaded via upload_batch_file().
            endpoint:          Which API endpoint to run ("/v1/chat/completions" or "/v1/embeddings").
            completion_window: How long the batch may run ("24h").
            metadata:          Optional key-value metadata dict.
        """
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/batches"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload: Dict[str, Any] = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
            "completion_window": completion_window,
        }
        if metadata:
            payload["metadata"] = metadata

        session = await self._get_session()
        async with session.post(url, headers=headers, json=payload, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            return Batch(**(await resp.json()))

    async def get_batch(
        self,
        batch_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Batch:
        """Retrieve the current status of a batch job."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/batches/{batch_id}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        session = await self._get_session()
        async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            return Batch(**(await resp.json()))

    async def list_batches(
        self,
        after: Optional[str] = None,
        limit: int = 20,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> BatchListResponse:
        """List batch jobs, newest first."""
        token = await self._get_token(credentials=credentials, scope=scope)
        params: Dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        url = f"{base_url or self.base_url}/batches"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        session = await self._get_session()
        async with session.get(url, headers=headers, params=params, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            return BatchListResponse(**(await resp.json()))

    async def cancel_batch(
        self,
        batch_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Batch:
        """Request cancellation of a running batch job."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{base_url or self.base_url}/batches/{batch_id}/cancel"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        session = await self._get_session()
        async with session.post(url, headers=headers, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            return Batch(**(await resp.json()))

    async def get_batch_results(
        self,
        batch_id: str,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> List[BatchResultItem]:
        """Download and parse results of a completed batch.

        Downloads the output file and parses every JSONL line into
        BatchResultItem.  Raises ValueError if the batch is not yet complete.
        """
        batch = await self.get_batch(batch_id, credentials=credentials,
                                     scope=scope, base_url=base_url)
        if not batch.is_done:
            raise ValueError(
                f"Batch {batch_id!r} is not done yet (status={batch.status!r}). "
                "Poll get_batch() until is_done=True."
            )
        if not batch.output_file_id:
            raise ValueError(
                f"Batch {batch_id!r} has no output file "
                f"(status={batch.status!r}, may have failed entirely)."
            )
        raw = await self.get_file_content(batch.output_file_id,
                                          credentials=credentials,
                                          scope=scope, base_url=base_url)
        results = []
        for line in raw.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                results.append(BatchResultItem(**json.loads(line)))
            except Exception as exc:
                logger.warning("Failed to parse batch result line: %s — %s", line[:120], exc)
        return results

    async def wait_for_batch(
        self,
        batch_id: str,
        poll_interval: float = 10.0,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Batch:
        """Poll until the batch reaches a terminal state, then return it.

        Args:
            poll_interval: Seconds between status checks (default 10).
        """
        import asyncio as _asyncio
        while True:
            batch = await self.get_batch(batch_id, credentials=credentials,
                                         scope=scope, base_url=base_url)
            logger.info(
                "Batch %s status=%s (%s/%s completed)",
                batch_id, batch.status,
                batch.request_counts.completed if batch.request_counts else "?",
                batch.request_counts.total if batch.request_counts else "?",
            )
            if batch.is_done:
                return batch
            await _asyncio.sleep(poll_interval)

    async def tts(
        self,
        text: str,
        voice: Optional[str] = None,
        format: str = "wav",
        credentials: Optional[str] = None,
        scope: Optional[str] = "SALUTE_SPEECH_PERS",
    ) -> bytes:
        """Text-to-Speech synthesis."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{self.SPEECH_BASE_URL}/text:synthesize"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/text",
            "Accept": f"audio/{format}",
        }

        params = {}
        if voice:
            params["voice"] = voice

        session = await self._get_session()
        async with session.post(url, headers=headers, data=text.encode("utf-8"), params=params, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            return await resp.read()

    # ------------------------------------------------------------------
    # GigaDark API methods (agent API for GigaChat-2-Pro-Dark)
    # ------------------------------------------------------------------

    @_api_retry()
    async def gigadark_query(
        self,
        messages: List[Dict[str, str]],
        client_agent_name: str = "CI00611872_CI12621384",
        model_name: str = "GigaChat-2-Pro-Dark",
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        password: Optional[str] = None,
    ) -> ChatResponse:
        """Query GigaDark (GigaChat-2-Pro-Dark) via agent API with client certificate auth.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            client_agent_name: Client agent identifier
            model_name: Model name (default: GigaChat-2-Pro-Dark)
            credentials: Optional credentials for authentication
            scope: Optional scope for authentication
            base_url: Override base URL
            password: Optional password for authentication

        Returns:
            ChatResponse with model output
        """
        import uuid

        url = f"{base_url or self.GIGADARK_BASE_URL}/query/model"

        payload = {
            "client_agent_name": client_agent_name,
            "model_name": model_name,
            "query_id": str(uuid.uuid4()),
            "messages": [
                {"role": "system", "content": "You are a helpful assistant"},
                *messages
            ]
        }

        c_auth_url, c_base_url, use_pw = self._resolve_contour(is_ift=True, is_advanced=None)
        token = await self._get_token(
            credentials=credentials,
            scope=scope,
            is_ift=use_pw,
            password=password,
            auth_url=c_auth_url,
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-identification-system": client_agent_name,
        }

        sem = await self._get_semaphore()
        async with sem:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload, ssl=self._ssl_context) as resp:
                await self._handle_response(resp)
                data = await resp.json()

                # Convert GigaDark response to ChatResponse format
                content = data.get("reply", "")
                return ChatResponse(
                    choices=[{
                        "message": {"role": "assistant", "content": content},
                        "delta": None,
                        "index": 0,
                        "finish_reason": "stop"
                    }],
                    created=int(time.time()),
                    model=model_name,
                    usage=None,
                    object="chat.completion"
                )

    # ------------------------------------------------------------------
    # Banking IFT API methods
    # ------------------------------------------------------------------

    @_api_retry()
    async def banking_ift_chat(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        password: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat request via Banking IFT API with TLS client certificate auth.

        Args:
            payload: Chat payload (dict or ChatPayload)
            credentials: Optional credentials for authentication
            scope: Optional scope for authentication
            base_url: Override base URL
            password: Optional password for authentication

        Returns:
            ChatResponse with model output
        """
        if isinstance(payload, dict):
            payload = ChatPayload(**payload)

        url = f"{base_url or self.BANKING_IFT_BASE_URL}/chat/completions"

        c_auth_url, c_base_url, use_pw = self._resolve_contour(is_ift=True, is_advanced=None)
        token = await self._get_token(
            credentials=credentials,
            scope=scope,
            is_ift=use_pw,
            password=password,
            auth_url=c_auth_url,
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        sem = await self._get_semaphore()
        async with sem:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload.dict(exclude_none=True), ssl=self._ssl_context) as resp:
                await self._handle_response(resp)
                data = await resp.json()
                return ChatResponse(**data)

    async def banking_ft_stream(
        self,
        payload: Union[Dict[str, Any], ChatPayload],
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        base_url: Optional[str] = None,
        password: Optional[str] = None,
    ) -> AsyncGenerator[ChatResponse, None]:
        """Stream chat responses via Banking IFT API.

        Args:
            payload: Chat payload (dict or ChatPayload)
            credentials: Optional credentials for authentication
            scope: Optional scope for authentication
            base_url: Override base URL
            password: Optional password for authentication

        Yields:
            ChatResponse chunks
        """
        if isinstance(payload, dict):
            payload = ChatPayload(**payload)
        payload.stream = True

        url = f"{base_url or self.BANKING_IFT_BASE_URL}/chat/completions"

        c_auth_url, c_base_url, use_pw = self._resolve_contour(is_ift=True, is_advanced=None)
        token = await self._get_token(
            credentials=credentials, scope=scope, is_ift=use_pw, password=password,
            auth_url=c_auth_url,
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        sem = await self._get_semaphore()
        async with sem:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload.dict(exclude_none=True), ssl=self._ssl_context) as resp:
                await self._handle_response(resp)
                buffer = ""
                async for chunk in resp.content.iter_any():
                    buffer += chunk.decode("utf-8")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        try:
                            yield ChatResponse(**json.loads(data_str))
                        except json.JSONDecodeError:
                            logger.warning("SSE parse error, skipping chunk: %.100s", data_str)


    async def stt(
        self,
        audio: Union[str, bytes],
        credentials: Optional[str] = None,
        scope: Optional[str] = "SALUTE_SPEECH_PERS",
    ) -> str:
        """Speech-to-Text transcription."""
        token = await self._get_token(credentials=credentials, scope=scope)
        url = f"{self.SPEECH_BASE_URL}/speech:recognize"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "audio/x-pcm;bit=16;rate=16000", # Example format, adjust as needed
        }

        if isinstance(audio, str):
            with open(audio, "rb") as f:
                content = f.read()
        else:
            content = audio

        session = await self._get_session()
        async with session.post(url, headers=headers, data=content, ssl=self._ssl_context) as resp:
            await self._handle_response(resp)
            data = await resp.json()
            # The structure for SaluteSpeech result is usually 'result': ['transcription']
            return " ".join(data.get("result", []))
