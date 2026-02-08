"""gRPC server — custom HTTP/2 implementation using h2."""

from __future__ import annotations

import asyncio
import ssl
from typing import TYPE_CHECKING, Any

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import (
    ConnectionTerminated,
    DataReceived,
    RemoteSettingsChanged,
    RequestReceived,
    StreamEnded,
    StreamReset,
    WindowUpdated,
)
from h2.exceptions import ProtocolError, StreamClosedError

from microapi._logging import get_logger
from microapi.protocol import MethodType, Request, Response, StatusCode
from microapi.serialization import deserialize, serialize
from microapi.transport.base import TransportServer
from microapi.transport.grpc.codec import decode_messages, encode_message
from microapi.types import Stream

if TYPE_CHECKING:
    from microapi.routing import Router

logger = get_logger("transport.grpc")

IO_TIMEOUT = 30.0
MAX_CONCURRENT_STREAMS = 128


class _StreamState:
    """Per-HTTP/2-stream state."""

    __slots__ = ("service", "method", "buf", "ended", "metadata")

    def __init__(self) -> None:
        self.service: str = ""
        self.method: str = ""
        self.buf: bytes = b""
        self.ended: bool = False
        self.metadata: dict[str, str] = {}


class GRPCProtocol(asyncio.Protocol):
    """asyncio Protocol that speaks gRPC over HTTP/2."""

    def __init__(self, router: Router, config: H2Configuration) -> None:
        self._router = router
        self._h2 = H2Connection(config=config)
        self._transport: asyncio.Transport | None = None
        self._streams: dict[int, _StreamState] = {}
        self._flow_waiters: dict[int, asyncio.Future[None]] = {}

    # -- asyncio.Protocol callbacks ---------------------------------------

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]
        self._transport = transport
        self._h2.initiate_connection()
        self._flush()

    def connection_lost(self, exc: Exception | None) -> None:
        for fut in self._flow_waiters.values():
            if not fut.done():
                fut.cancel()
        self._streams.clear()

    def data_received(self, data: bytes) -> None:
        try:
            events = self._h2.receive_data(data)
        except ProtocolError:
            self._transport and self._transport.close()
            return

        for event in events:
            if isinstance(event, RequestReceived):
                self._on_request(event)
            elif isinstance(event, DataReceived):
                self._on_data(event)
            elif isinstance(event, StreamEnded):
                self._on_stream_ended(event)
            elif isinstance(event, WindowUpdated):
                self._on_window_updated(event)
            elif isinstance(event, StreamReset):
                self._streams.pop(event.stream_id, None)
            elif isinstance(event, RemoteSettingsChanged):
                pass
            elif isinstance(event, ConnectionTerminated):
                self._transport and self._transport.close()
                return

        self._flush()

    # -- h2 event handlers ------------------------------------------------

    def _on_request(self, event: RequestReceived) -> None:
        headers: dict[str, str] = {}
        for k, v in event.headers:
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            headers[key] = val

        path = headers.get(":path", "")

        state = _StreamState()
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            state.service = parts[0]
            state.method = parts[1]
        # Collect metadata from non-pseudo-headers
        for key, val in headers.items():
            if not key.startswith(":") and key not in ("content-type", "te", "user-agent"):
                state.metadata[key] = val

        self._streams[event.stream_id] = state

    def _on_data(self, event: DataReceived) -> None:
        state = self._streams.get(event.stream_id)
        if state is not None:
            state.buf += event.data
        self._h2.acknowledge_received_data(event.flow_controlled_length, event.stream_id)

    def _on_stream_ended(self, event: StreamEnded) -> None:
        state = self._streams.get(event.stream_id)
        if state is None:
            return
        state.ended = True
        asyncio.ensure_future(self._handle_stream(event.stream_id, state))

    def _on_window_updated(self, event: WindowUpdated) -> None:
        waiter = self._flow_waiters.pop(event.stream_id, None)
        if waiter and not waiter.done():
            waiter.set_result(None)
        # Also check connection-level (stream_id=0)
        waiter = self._flow_waiters.pop(0, None)
        if waiter and not waiter.done():
            waiter.set_result(None)

    # -- request handling -------------------------------------------------

    async def _handle_stream(self, stream_id: int, state: _StreamState) -> None:
        """Process a completed request on *stream_id*."""
        try:
            # Decode gRPC messages
            messages, _ = decode_messages(state.buf)
            payload_data = messages[0] if messages else b"{}"

            try:
                payload = deserialize(payload_data)
            except Exception:
                payload = {}

            method_type = MethodType.UNARY
            try:
                method_type = self._router.get_method_type(state.service, state.method)
            except Exception:
                pass

            request = Request(
                service=state.service,
                method=state.method,
                payload=payload if isinstance(payload, dict) else {},
                metadata=state.metadata,
            )

            # Handle client-streaming: feed all messages into a Stream
            client_stream: Stream[Any] | None = None
            if method_type in (MethodType.CLIENT_STREAMING, MethodType.BIDI_STREAMING):
                client_stream = Stream()
                for msg_bytes in messages:
                    msg_data: Any = None
                    try:
                        msg_data = deserialize(msg_bytes)
                        method_info = self._router.get_method_info(state.service, state.method)
                        if method_info.stream_input_type:
                            obj = method_info.stream_input_type.model_validate(msg_data)
                            await client_stream._feed(obj)
                        else:
                            await client_stream._feed(msg_data)
                    except Exception:
                        if msg_data is not None:
                            await client_stream._feed(msg_data)
                await client_stream._close()

            response = await self._router.handle_request(request, client_stream)

            # Send response headers
            resp_headers = [
                (":status", "200"),
                ("content-type", "application/grpc+json"),
            ]
            try:
                self._h2.send_headers(stream_id, resp_headers)
                self._flush()
            except (StreamClosedError, ProtocolError):
                return

            # Send response data
            if response.is_streaming and hasattr(response.payload, "__aiter__"):
                async for item in response.payload:
                    item_bytes = serialize(item)
                    frame = encode_message(item_bytes)
                    await self._send_data(stream_id, frame)
            elif response.payload is not None:
                resp_bytes = serialize(response.payload)
                frame = encode_message(resp_bytes)
                await self._send_data(stream_id, frame)

            # Send trailers
            grpc_status = "0" if response.status_code == StatusCode.OK else str(response.status_code.value)
            grpc_message = response.error or ""
            trailers = [
                ("grpc-status", grpc_status),
                ("grpc-message", grpc_message),
            ]
            try:
                self._h2.send_headers(stream_id, trailers, end_stream=True)
                self._flush()
            except (StreamClosedError, ProtocolError):
                pass

        except Exception as exc:
            logger.exception("Error handling stream %d", stream_id)
            try:
                trailers = [
                    (":status", "200"),
                    ("content-type", "application/grpc+json"),
                    ("grpc-status", "13"),
                    ("grpc-message", str(exc)),
                ]
                self._h2.send_headers(stream_id, trailers, end_stream=True)
                self._flush()
            except (StreamClosedError, ProtocolError):
                pass
        finally:
            self._streams.pop(stream_id, None)

    # -- data sending with flow control -----------------------------------

    async def _send_data(self, stream_id: int, data: bytes) -> None:
        """Send *data* on *stream_id* respecting h2 flow control."""
        idx = 0
        while idx < len(data):
            try:
                window = self._h2.local_flow_control_window(stream_id)
            except StreamClosedError:
                return
            max_frame = self._h2.max_outbound_frame_size
            chunk_size = min(window, max_frame, len(data) - idx)

            if chunk_size <= 0:
                # Wait for window update
                loop = asyncio.get_running_loop()
                fut: asyncio.Future[None] = loop.create_future()
                self._flow_waiters[stream_id] = fut
                try:
                    await asyncio.wait_for(fut, timeout=IO_TIMEOUT)
                except asyncio.TimeoutError:
                    return
                continue

            chunk = data[idx : idx + chunk_size]
            try:
                self._h2.send_data(stream_id, chunk)
            except (StreamClosedError, ProtocolError):
                return
            self._flush()
            idx += chunk_size

    # -- helpers ----------------------------------------------------------

    def _flush(self) -> None:
        data = self._h2.data_to_send()
        if data and self._transport:
            self._transport.write(data)


class GRPCServer(TransportServer):
    """gRPC server over HTTP/2 (prior-knowledge, no TLS-ALPN required)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        ssl_context: ssl.SSLContext | None = None,
        max_streams: int = MAX_CONCURRENT_STREAMS,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_streams = max_streams
        self._server: asyncio.Server | None = None
        self._router: Router | None = None

    async def start(self, router: Router) -> None:
        self._router = router
        config = H2Configuration(client_side=False, header_encoding="utf-8")

        loop = asyncio.get_running_loop()
        self._server = await loop.create_server(
            lambda: GRPCProtocol(router, config),
            self.host,
            self.port,
            ssl=self.ssl_context,
        )
        logger.info("gRPC server listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("gRPC server stopped")

    async def serve_forever(self) -> None:
        if self._server:
            await self._server.serve_forever()
