"""HTTP transport client using aiohttp."""

from __future__ import annotations

from typing import Any, AsyncIterator

import aiohttp

from microapi._logging import get_logger
from microapi.exceptions import TransportError
from microapi.serialization import deserialize, serialize
from microapi.transport.base import TransportClient

logger = get_logger("transport.http.client")


class HTTPClient(TransportClient):
    """HTTP client for communicating with a MicroAPI HTTP server."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080") -> None:
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        logger.debug("HTTP client connected to %s", self.base_url)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def request(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("Not connected. Call connect() first.")

        url = f"{self.base_url}/{service}/{method}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if metadata:
            for k, v in metadata.items():
                headers[f"X-MicroAPI-{k}"] = v

        body = serialize(payload or {})

        async with self._session.post(url, data=body, headers=headers) as resp:
            if resp.status >= 400:
                error_body = await resp.text()
                raise TransportError(f"HTTP {resp.status}: {error_body}")

            data = await resp.read()
            return deserialize(data)

    async def request_stream(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a request and iterate over NDJSON streaming response."""
        if not self._session:
            raise RuntimeError("Not connected. Call connect() first.")

        url = f"{self.base_url}/{service}/{method}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if metadata:
            for k, v in metadata.items():
                headers[f"X-MicroAPI-{k}"] = v

        body = serialize(payload or {})

        async with self._session.post(url, data=body, headers=headers) as resp:
            if resp.status >= 400:
                error_body = await resp.text()
                raise TransportError(f"HTTP {resp.status}: {error_body}")

            async for line in resp.content:
                line = line.strip()
                if line:
                    yield deserialize(line)
