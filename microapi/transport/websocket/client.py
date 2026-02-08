"""WebSocket transport client."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from microapi._logging import get_logger
from microapi.exceptions import TransportError
from microapi.protocol import Envelope, MessageType
from microapi.serialization import deserialize, serialize
from microapi.transport.base import TransportClient

logger = get_logger("transport.websocket.client")


class WebSocketClient(TransportClient):
    """WebSocket client for communicating with a MicroAPI WS server."""

    def __init__(self, url: str = "ws://127.0.0.1:8765") -> None:
        self.url = url
        self._ws: ClientConnection | None = None
        self._pending: dict[str, asyncio.Future[Envelope]] = {}
        self._stream_queues: dict[str, asyncio.Queue[Envelope | None]] = {}
        self._recv_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self.url)
        self._recv_task = asyncio.create_task(self._receive_loop())
        logger.debug("WebSocket client connected to %s", self.url)

    async def close(self) -> None:
        if self._recv_task:
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._recv_task
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def request(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._ws:
            raise RuntimeError("Not connected")

        envelope = Envelope(
            type=MessageType.REQUEST,
            service=service,
            method=method,
            payload=payload,
            metadata=metadata or {},
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Envelope] = loop.create_future()
        self._pending[envelope.id] = future

        await self._ws.send(serialize(envelope.to_dict()))

        resp_envelope = await asyncio.wait_for(future, timeout=30.0)

        if resp_envelope.error:
            raise TransportError(resp_envelope.error)
        return resp_envelope.payload or {}

    async def request_stream(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a request and iterate over streaming responses."""
        if not self._ws:
            raise RuntimeError("Not connected")

        envelope = Envelope(
            type=MessageType.REQUEST,
            service=service,
            method=method,
            payload=payload,
            metadata=metadata or {},
        )

        queue: asyncio.Queue[Envelope | None] = asyncio.Queue()
        self._stream_queues[envelope.id] = queue

        await self._ws.send(serialize(envelope.to_dict()))

        while True:
            item = await queue.get()
            if item is None:
                break
            if item.payload is not None:
                yield item.payload

        self._stream_queues.pop(envelope.id, None)

    async def _receive_loop(self) -> None:
        """Background task that routes incoming messages."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    data = deserialize(raw if isinstance(raw, bytes) else raw.encode())
                    envelope = Envelope.from_dict(data)
                except Exception:
                    continue

                msg_id = envelope.id

                if envelope.type == MessageType.RESPONSE:
                    fut = self._pending.pop(msg_id, None)
                    if fut and not fut.done():
                        fut.set_result(envelope)
                    # Also signal end to any streaming queue
                    queue = self._stream_queues.pop(msg_id, None)
                    if queue:
                        await queue.put(None)

                elif envelope.type == MessageType.STREAM_PUSH:
                    queue = self._stream_queues.get(msg_id)
                    if queue:
                        await queue.put(envelope)

                elif envelope.type == MessageType.STREAM_END:
                    queue = self._stream_queues.pop(msg_id, None)
                    if queue:
                        await queue.put(None)

        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
            pass
