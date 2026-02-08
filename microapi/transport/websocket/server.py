"""WebSocket transport server."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import websockets
from websockets.asyncio.server import Server, ServerConnection

from microapi._logging import get_logger
from microapi.protocol import (
    Envelope,
    MessageType,
    MethodType,
    Request,
    StatusCode,
)
from microapi.serialization import deserialize, serialize, to_dict
from microapi.transport.base import TransportServer
from microapi.types import Stream

if TYPE_CHECKING:
    from microapi.routing import Router

logger = get_logger("transport.websocket")


class WebSocketServer(TransportServer):
    """WebSocket transport server.

    All communication happens over a single WebSocket connection with
    multiplexed request/response messages identified by ``id``.

    Wire format (JSON)::

        {"type": "request", "service": "users", "method": "get_user",
         "id": "abc123", "payload": {...}, "metadata": {...}}
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._server: Server | None = None
        self._router: Router | None = None

    async def start(self, router: Router) -> None:
        self._router = router
        self._server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
        )
        logger.info("WebSocket server listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("WebSocket server stopped")

    async def serve_forever(self) -> None:
        if self._server:
            await self._server.serve_forever()

    async def _handle_connection(self, ws: ServerConnection) -> None:
        """Handle a single WebSocket connection (multiplexed)."""
        assert self._router is not None

        # Collect stream messages for client streaming
        stream_buffers: dict[str, Stream[Any]] = {}

        try:
            async for raw_message in ws:
                try:
                    data = deserialize(raw_message if isinstance(raw_message, bytes) else raw_message.encode())
                    envelope = Envelope.from_dict(data)
                except Exception:
                    await ws.send(serialize({"error": "Invalid message format"}))
                    continue

                if envelope.type == MessageType.REQUEST:
                    asyncio.ensure_future(
                        self._handle_request(ws, envelope)
                    )
                elif envelope.type == MessageType.STREAM_PUSH:
                    await self._handle_stream_push(envelope, stream_buffers)
                elif envelope.type == MessageType.STREAM_END:
                    await self._handle_stream_end(ws, envelope, stream_buffers)

        except websockets.exceptions.ConnectionClosed:
            pass

    async def _handle_request(self, ws: ServerConnection, envelope: Envelope) -> None:
        """Handle a unary or server-streaming request."""
        assert self._router is not None

        request = Request(
            service=envelope.service,
            method=envelope.method,
            payload=envelope.payload,
            metadata=envelope.metadata,
            id=envelope.id,
        )

        try:
            method_type = self._router.get_method_type(envelope.service, envelope.method)
        except Exception:
            method_type = MethodType.UNARY

        response = await self._router.handle_request(request)

        if response.is_streaming and hasattr(response.payload, "__aiter__"):
            # Server streaming: send multiple stream_push messages
            async for item in response.payload:
                push_envelope = Envelope(
                    type=MessageType.STREAM_PUSH,
                    service=envelope.service,
                    method=envelope.method,
                    id=envelope.id,
                    payload=to_dict(item) if hasattr(item, "model_dump") else item,
                )
                await ws.send(serialize(push_envelope.to_dict()))

            # Send stream end
            end_envelope = Envelope(
                type=MessageType.STREAM_END,
                id=envelope.id,
            )
            await ws.send(serialize(end_envelope.to_dict()))
        else:
            # Unary response
            resp_envelope = Envelope(
                type=MessageType.RESPONSE,
                service=envelope.service,
                method=envelope.method,
                id=envelope.id,
                payload=response.payload if isinstance(response.payload, dict) else None,
                error=response.error,
                status_code=response.status_code.value,
            )
            await ws.send(serialize(resp_envelope.to_dict()))

    async def _handle_stream_push(
        self,
        envelope: Envelope,
        stream_buffers: dict[str, Stream[Any]],
    ) -> None:
        """Buffer a client stream message."""
        stream_id = envelope.id
        if stream_id not in stream_buffers:
            stream_buffers[stream_id] = Stream()

        stream = stream_buffers[stream_id]
        if envelope.payload is not None:
            # Try to validate against the method's stream input type
            try:
                assert self._router is not None
                method_info = self._router.get_method_info(envelope.service, envelope.method)
                if method_info.stream_input_type:
                    obj = method_info.stream_input_type.model_validate(envelope.payload)
                    await stream._feed(obj)
                else:
                    await stream._feed(envelope.payload)
            except Exception:
                await stream._feed(envelope.payload)

    async def _handle_stream_end(
        self,
        ws: ServerConnection,
        envelope: Envelope,
        stream_buffers: dict[str, Stream[Any]],
    ) -> None:
        """Finalize a client stream and dispatch the request."""
        assert self._router is not None

        stream_id = envelope.id
        stream = stream_buffers.pop(stream_id, None)
        if stream is None:
            stream = Stream()

        await stream._close()

        request = Request(
            service=envelope.service,
            method=envelope.method,
            payload=envelope.payload,
            metadata=envelope.metadata,
            id=envelope.id,
        )

        response = await self._router.handle_request(request, client_stream=stream)

        if response.is_streaming and hasattr(response.payload, "__aiter__"):
            async for item in response.payload:
                push_envelope = Envelope(
                    type=MessageType.STREAM_PUSH,
                    id=stream_id,
                    payload=to_dict(item) if hasattr(item, "model_dump") else item,
                )
                await ws.send(serialize(push_envelope.to_dict()))

        # Final response / end
        resp_envelope = Envelope(
            type=MessageType.RESPONSE if not response.is_streaming else MessageType.STREAM_END,
            id=stream_id,
            payload=response.payload if isinstance(response.payload, dict) else None,
            error=response.error,
            status_code=response.status_code.value,
        )
        await ws.send(serialize(resp_envelope.to_dict()))
