import asyncio
import base64
import datetime
import logging
import ssl
import uuid
from typing import Dict, Optional, Tuple, Union

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from .exceptions import AuthenticationError

logger = logging.getLogger(__name__)

class AuthToken:
    def __init__(self, token: str, expires_at: int):
        self.token = token
        self.expires_at = expires_at / 1000  # Convert to seconds

    @property
    def is_expired(self) -> bool:
        # Re-obtain token 1 minute before expiration
        return datetime.datetime.now().timestamp() > (self.expires_at - 60)

class TokenManager:
    def __init__(self):
        self._tokens: Dict[Tuple[str, str, str], AuthToken] = {}
        self._locks: Dict[Tuple[str, str, str], asyncio.Lock] = {}

    def _get_key(self, credentials: str, scope: str, auth_url: str) -> Tuple[str, str, str]:
        return (credentials, scope, auth_url)

    async def get_token(
        self,
        session: aiohttp.ClientSession,
        credentials: str,
        scope: str,
        auth_url: str,
        ssl_context: Union[ssl.SSLContext, bool],
        is_ift: bool = False,
        password: Optional[str] = None
    ) -> str:
        key = self._get_key(credentials, scope, auth_url)

        if key not in self._tokens or self._tokens[key].is_expired:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()

            async with self._locks[key]:
                # Double check after acquiring lock
                if key not in self._tokens or self._tokens[key].is_expired:
                    if is_ift:
                        token = await self._authenticate_ift(session, credentials, password, auth_url, ssl_context)
                    else:
                        token = await self._authenticate_oauth(session, credentials, scope, auth_url, ssl_context)
                    self._tokens[key] = token

        return self._tokens[key].token

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _authenticate_oauth(
        self,
        session: aiohttp.ClientSession,
        credentials: str,
        scope: str,
        auth_url: str,
        ssl_context: Union[ssl.SSLContext, bool]
    ) -> AuthToken:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {credentials}"
        }
        data = {"scope": scope}

        async with session.post(auth_url, headers=headers, data=data, ssl=ssl_context) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise AuthenticationError(f"OAuth failed: {resp.status} - {text}", status_code=resp.status, response_text=text)

            payload = await resp.json()
            return AuthToken(payload["access_token"], payload["expires_at"])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _authenticate_ift(
        self,
        session: aiohttp.ClientSession,
        login: str,
        password: str,
        auth_url: str,
        ssl_context: Union[ssl.SSLContext, bool]
    ) -> AuthToken:
        auth = aiohttp.BasicAuth(login, password)
        async with session.post(auth_url, auth=auth, ssl=ssl_context) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise AuthenticationError(f"IFT Auth failed: {resp.status} - {text}", status_code=resp.status, response_text=text)

            payload = await resp.json()
            # IFT format might differ, assuming 'tok' and 'exp' based on existing client
            return AuthToken(payload["tok"], payload.get("exp", payload.get("expires_at", 0)) * 1000)
