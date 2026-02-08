"""gRPC client — custom HTTP/2 implementation using h2."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import AsyncIterator
from typing import Any

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import (
    DataReceived,
    ResponseReceived,
    StreamEnded,
    StreamReset,
    WindowUpdated,
)
from h2.exceptions import ProtocolError

from microapi._logging import get_logger
from microapi.serialization import deserialize, serialize
from microapi.transport.base import TransportClient
from microapi.transport.grpc.codec import decode_messages, encode_message

logger = get_logger("transport.grpc.client")

IO_TIMEOUT = 30.0


class _ClientStreamState:
    """Tracks per-stream state on the client side."""

    __slots__ = ("headers", "data_buf", "ended", "trailers", "event")

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.data_buf: bytes = b""
        self.ended: bool = False
        self.trailers: dict[str, str] = {}
        self.event: asyncio.Event = asyncio.Event()


class GRPCClientProtocol(asyncio.Protocol):
    """asyncio Protocol for gRPC client connections over HTTP/2."""

    def __init__(self, config: H2Configuration) -> None:
        self._h2 = H2Connection(config=config)
        self._transport: asyncio.Transport | None = None
        self._streams: dict[int, _ClientStreamState] = {}
        self._flow_waiters: dict[int, asyncio.Future[None]] = {}
        self._connected = asyncio.Event()

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]
        self._transport = transport
        self._h2.initiate_connection()
        self._flush()
        self._connected.set()

    def connection_lost(self, exc: Exception | None) -> None:
        for state in self._streams.values():
            state.ended = True
            state.event.set()
        for fut in self._flow_waiters.values():
            if not fut.done():
                fut.cancel()

    def data_received(self, data: bytes) -> None:
        try:
            events = self._h2.receive_data(data)
        except ProtocolError:
            return

        for event in events:
            if isinstance(event, ResponseReceived):
                state = self._streams.get(event.stream_id)
                if state:
                    for k, v in event.headers:
                        key = k.decode() if isinstance(k, bytes) else k
                        val = v.decode() if isinstance(v, bytes) else v
                        state.headers[key] = val
            elif isinstance(event, DataReceived):
                state = self._streams.get(event.stream_id)
                if state:
                    state.data_buf += event.data
                self._h2.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
            elif isinstance(event, (StreamEnded, StreamReset)):
                state = self._streams.get(event.stream_id)
                if state:
                    state.ended = True
                    state.event.set()
            elif isinstance(event, WindowUpdated):
                waiter = self._flow_waiters.pop(event.stream_id, None)
                if waiter and not waiter.done():
                    waiter.set_result(None)

        self._flush()

    def _flush(self) -> None:
        data = self._h2.data_to_send()
        if data and self._transport:
            self._transport.write(data)

    # -- public API -------------------------------------------------------

    def new_stream(self) -> int:
        stream_id = self._h2.get_next_available_stream_id()
        self._streams[stream_id] = _ClientStreamState()
        return stream_id

    def send_request(
        self,
        stream_id: int,
        service: str,
        method: str,
        payload: bytes,
        metadata: dict[str, str] | None = None,
    ) -> None:
        headers = [
            (":method", "POST"),
            (":scheme", "http"),
            (":path", f"/{service}/{method}"),
            (":authority", "localhost"),
            ("content-type", "application/grpc+json"),
            ("te", "trailers"),
        ]
        if metadata:
            for k, v in metadata.items():
                headers.append((k, v))

        frame = encode_message(payload)
        self._h2.send_headers(stream_id, headers)
        self._h2.send_data(stream_id, frame, end_stream=True)
        self._flush()

    async def wait_response(self, stream_id: int) -> _ClientStreamState:
        state = self._streams[stream_id]
        await asyncio.wait_for(state.event.wait(), timeout=IO_TIMEOUT)
        return state


class GRPCClient(TransportClient):
    """gRPC client that connects to a MicroAPI gRPC server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self._protocol: GRPCClientProtocol | None = None
        self._transport: asyncio.Transport | None = None

    async def connect(self) -> None:
        config = H2Configuration(client_side=True, header_encoding="utf-8")
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_connection(
            lambda: GRPCClientProtocol(config),
            self.host,
            self.port,
            ssl=self.ssl_context,
        )
        self._transport = transport
        self._protocol = protocol
        await self._protocol._connected.wait()
        logger.debug("Connected to gRPC server at %s:%d", self.host, self.port)

    async def close(self) -> None:
        if self._transport:
            self._transport.close()
            self._protocol = None
            self._transport = None

    async def request(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._protocol:
            raise RuntimeError("Not connected")

        payload_bytes = serialize(payload or {})
        stream_id = self._protocol.new_stream()
        self._protocol.send_request(stream_id, service, method, payload_bytes, metadata)

        state = await self._protocol.wait_response(stream_id)

        # Decode response
        messages, _ = decode_messages(state.data_buf)
        if messages:
            result: dict[str, Any] = deserialize(messages[0])
            return result
        return {}

    async def request_stream(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a request and iterate over streaming response frames."""
        if not self._protocol:
            raise RuntimeError("Not connected")

        payload_bytes = serialize(payload or {})
        stream_id = self._protocol.new_stream()
        self._protocol.send_request(stream_id, service, method, payload_bytes, metadata)

        state = await self._protocol.wait_response(stream_id)

        messages, _ = decode_messages(state.data_buf)
        for msg in messages:
            item: dict[str, Any] = deserialize(msg)
            yield item
