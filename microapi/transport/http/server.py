"""HTTP transport server using aiohttp."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from aiohttp import web

from microapi._logging import get_logger
from microapi.protocol import MethodType, Request, StatusCode
from microapi.serialization import deserialize, serialize
from microapi.transport.base import TransportServer
from microapi.types import Stream

if TYPE_CHECKING:
    from microapi.routing import Router

logger = get_logger("transport.http")


class HTTPServer(TransportServer):
    """HTTP/1.1 transport server using aiohttp.

    Maps service methods to POST endpoints::

        POST /{service}/{method}
        Content-Type: application/json

        {"name": "Alice", "age": 30}
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        self.host = host
        self.port = port
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._router: Router | None = None

    async def start(self, router: Router) -> None:
        self._router = router
        self._app = web.Application()
        self._app.router.add_post("/{service}/{method}", self._handle_request)
        # Health check endpoint
        self._app.router.add_get("/health", self._health_check)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info("HTTP server listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("HTTP server stopped")

    async def serve_forever(self) -> None:
        # For HTTP, the runner keeps it alive; we just wait indefinitely
        while True:
            await asyncio.sleep(3600)

    async def _health_check(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _handle_request(self, http_request: web.Request) -> web.StreamResponse:
        assert self._router is not None

        service = http_request.match_info["service"]
        method = http_request.match_info["method"]

        # Parse body
        try:
            body = await http_request.read()
            payload = deserialize(body) if body else {}
        except Exception:
            return web.json_response(
                {"error": "Invalid JSON body"},
                status=400,
            )

        # Extract metadata from headers
        metadata: dict[str, str] = {}
        for key, value in http_request.headers.items():
            lower_key = key.lower()
            if lower_key.startswith("x-microapi-"):
                metadata[lower_key.removeprefix("x-microapi-")] = value

        # Determine method type and build request
        try:
            method_type = self._router.get_method_type(service, method)
        except Exception:
            return web.json_response(
                {"error": f"Method '{method}' not found in service '{service}'"},
                status=404,
            )

        rpc_request = Request(
            service=service,
            method=method,
            payload=payload if isinstance(payload, dict) else {},
            metadata=metadata,
        )

        # Handle client streaming (payload is a list of messages)
        client_stream: Stream[Any] | None = None
        if method_type in (MethodType.CLIENT_STREAMING, MethodType.BIDI_STREAMING):
            client_stream = Stream()
            if isinstance(payload, list):
                method_info = self._router.get_method_info(service, method)
                for item in payload:
                    if (
                        method_info.stream_input_type
                        and hasattr(method_info.stream_input_type, "model_validate")
                        and isinstance(item, dict)
                    ):
                        obj = method_info.stream_input_type.model_validate(item)
                        await client_stream._feed(obj)
                    else:
                        await client_stream._feed(item)
            await client_stream._close()

        response = await self._router.handle_request(rpc_request, client_stream)

        # Build HTTP response
        if response.error:
            status_map = {
                StatusCode.NOT_FOUND: 404,
                StatusCode.INVALID_ARGUMENT: 400,
                StatusCode.PERMISSION_DENIED: 403,
                StatusCode.UNAUTHENTICATED: 401,
                StatusCode.INTERNAL: 500,
            }
            http_status = status_map.get(response.status_code, 500)
            return web.json_response({"error": response.error}, status=http_status)

        if response.is_streaming and hasattr(response.payload, "__aiter__"):
            # Server streaming: return as JSON array using streaming response
            resp = web.StreamResponse(
                status=200,
                headers={"Content-Type": "application/x-ndjson"},
            )
            await resp.prepare(http_request)
            async for item in response.payload:
                chunk = serialize(item) + b"\n"
                await resp.write(chunk)
            await resp.write_eof()
            return resp

        return web.json_response(response.payload)
