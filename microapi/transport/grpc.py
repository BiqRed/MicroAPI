import asyncio
import io
import ssl
from typing import Dict, AsyncIterator

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.errors import ErrorCodes
from h2.events import RequestReceived, DataReceived, StreamEnded, StreamReset, WindowUpdated, RemoteSettingsChanged, \
    ConnectionTerminated
from h2.exceptions import ProtocolError, StreamClosedError
from h2.settings import SettingCodes

from microapi.transport.base import (
    Stream as BaseStream,
    Request, Response, Handler,
    TransportServer, TransportClient, Transport
)

MAX_BUFFER_SIZE = 1024 * 1024  # 1 MB
MAX_HEADER_SIZE = 8192  # 8 KB
MAX_QUEUE_SIZE = 100  # Maximum queue size
IO_TIMEOUT = 30.0  # Timeout for I/O operations


def _pack_message(message: bytes) -> bytes:
    """Packs a message into a gRPC frame format.

    Args:
        message (bytes): The message payload to pack.

    Returns:
        bytes: The packed gRPC frame, consisting of a 1-byte flag, 4-byte length, and the payload.
    """
    return b'\x00' + len(message).to_bytes(4, 'big') + message


class H2GRPCStream(BaseStream):
    """A stream for handling gRPC communication over HTTP/2.

    Attributes:
        proto (H2GRPCProtocol): The protocol instance managing the HTTP/2 connection.
        id (int): The unique stream identifier.
        _buf (asyncio.Queue): A queue for buffering received messages.
    """

    def __init__(self, proto: "H2GRPCProtocol", stream_id: int) -> None:
        """Initializes the H2GRPCStream.

        Args:
            proto (H2GRPCProtocol): The protocol instance managing the HTTP/2 connection.
            stream_id (int): The unique identifier for this stream.
        """
        self.proto = proto
        self.id = stream_id
        self._buf = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

    async def send(self, message: str) -> None:
        """Sends a message over the stream.

        Args:
            message (str): The message to send.

        Raises:
            ProtocolError: If the stream is closed or the connection encounters an error.
            asyncio.TimeoutError: If the send-operation times out.
        """
        try:
            frame = _pack_message(message.encode())
            await asyncio.wait_for(self.proto.send_with_flow(frame, self.id), timeout=IO_TIMEOUT)
        except (StreamClosedError, ProtocolError):
            self.proto.conn.end_stream(self.id)
            self.proto.flush()
            raise

    async def recv(self) -> str:
        """Receives a message from the stream.

        Returns:
            str: The received message decoded as a string.

        Raises:
            EOFError: If the stream is closed or no more data is available.
            asyncio.TimeoutError: If the receive-operation times out.
        """
        try:
            chunk = await asyncio.wait_for(self._buf.get(), timeout=IO_TIMEOUT)
            if chunk is None:
                raise EOFError()
            return chunk.decode('utf-8')
        except UnicodeDecodeError:
            raise ProtocolError("Invalid UTF-8 data received")

    async def close(self) -> None:
        """Closes the stream.

        Sends an end-stream signal to the HTTP/2 connection and flushes the data.
        """
        try:
            self.proto.conn.end_stream(self.id)
            self.proto.flush()
        except (StreamClosedError, ProtocolError):
            pass  # If the stream is already closed


class H2GRPCProtocol(asyncio.Protocol):
    """An asyncio protocol for handling gRPC over HTTP/2.

    Manages the HTTP/2 connection, processes incoming events, and delegates requests to the handler.

    Attributes:
        handler (Handler): The application handler for processing requests.
        conn (H2Connection): The HTTP/2 connection instance.
        max_streams (int): The maximum number of concurrent streams allowed.
        transport (asyncio.Transport | None): The underlying transport for the connection.
        streams (Dict[int, Dict]): A mapping of stream IDs to stream metadata.
        flow_futures (Dict[int, asyncio.Future]): A mapping of stream IDs to flow control futures.
    """

    def __init__(self, handler: Handler, config: H2Configuration, max_streams: int) -> None:
        """Initializes the H2GRPCProtocol.

        Args:
            handler (Handler): The application handler for processing requests.
            config (H2Configuration): The HTTP/2 configuration.
            max_streams (int): The maximum number of concurrent streams.

        Raises:
            ValueError: If max_streams is invalid.
        """
        if max_streams <= 0:
            raise ValueError("max_streams must be positive")
        self.handler = handler
        self.conn = H2Connection(config=config)
        self.max_streams = max_streams
        self.transport = None
        self.streams: Dict[int, Dict] = {}
        self.flow_futures: Dict[int, asyncio.Future] = {}

    def connection_made(self, transport: asyncio.Transport) -> None:
        """Called when a connection is established.

        Initializes the HTTP/2 connection and sets the maximum concurrent streams.

        Args:
            transport (asyncio.Transport): The transport for the connection.

        Raises:
            RuntimeError: If handler is not set.
        """
        if self.handler is None:
            raise RuntimeError("Handler must be set before connection is made")
        self.transport = transport
        self.conn.initiate_connection()
        self.conn.update_settings({SettingCodes.MAX_CONCURRENT_STREAMS: self.max_streams})
        self.flush()

    def data_received(self, data: bytes) -> None:
        """Processes incoming data from the HTTP/2 connection.

        Parses the data into HTTP/2 events and handles them accordingly. Events include
        request headers, data chunks, stream termination, and flow control updates.

        Args:
            data (bytes): The raw data received from the connection.
        """
        try:
            events = self.conn.receive_data(data)
        except ProtocolError:
            self.streams.clear()
            self.flow_futures.clear()
            self.transport.close()
            return

        for ev in events:
            sid = getattr(ev, 'stream_id', None)
            if isinstance(ev, RequestReceived):
                _headers = dict(ev.headers or [])
                path = _headers.get(':path', '').lstrip('/')
                if not path or '/' not in path:
                    self.conn.reset_stream(sid, ErrorCodes.PROTOCOL_ERROR)
                    continue
                try:
                    svc, mtd = path.split('/', 1)
                except ValueError:
                    self.conn.reset_stream(sid, ErrorCodes.PROTOCOL_ERROR)
                    continue

                meta = {
                    k: v for k, v in ev.headers
                    if not k.startswith(':') and k.islower() and len(v) < MAX_HEADER_SIZE
                }
                self.streams[sid] = {
                    'svc': svc, 'mtd': mtd,
                    'meta': meta, 'buf': io.BytesIO()
                }
            elif isinstance(ev, DataReceived):
                sd = self.streams.get(sid)
                if not sd:
                    self.conn.reset_stream(sid, ErrorCodes.PROTOCOL_ERROR)
                    continue
                if sd['buf'].tell() + len(ev.data) > MAX_BUFFER_SIZE:
                    self.conn.reset_stream(sid, ErrorCodes.ENHANCE_YOUR_CALM)
                    continue
                sd['buf'].write(ev.data)
                self.conn.acknowledge_received_data(ev.flow_controlled_length, sid)
            elif isinstance(ev, StreamEnded):
                sd = self.streams.pop(sid, None)
                if not sd:
                    continue
                payload = sd['buf'].getvalue()
                try:
                    decoded_payload = payload.decode('utf-8')
                except UnicodeDecodeError:
                    self.conn.reset_stream(sid, ErrorCodes.PROTOCOL_ERROR)
                    continue

                req = Request(
                    service=sd['svc'],
                    method=sd['mtd'],
                    payload=decoded_payload,
                    metadata=sd['meta'],
                    stream=H2GRPCStream(self, sid)
                )
                asyncio.create_task(self._handle(req, sid))
            elif isinstance(ev, StreamReset):
                self.streams.pop(sid, None)
                self.flow_futures.pop(sid, None)
            elif isinstance(ev, ConnectionTerminated):
                self.streams.clear()
                self.flow_futures.clear()
                self.transport.close()
                return
            elif isinstance(ev, WindowUpdated):
                fut = self.flow_futures.pop(sid, None)
                if fut:
                    fut.set_result(None)
            elif isinstance(ev, RemoteSettingsChanged):
                if SettingCodes.INITIAL_WINDOW_SIZE in ev.changed_settings:
                    for fut in self.flow_futures.values():
                        fut.set_result(None)
                    self.flow_futures.clear()
        self.flush()

    def flush(self) -> None:
        """Flushes pending data to the transport.

        Sends any buffered HTTP/2 data to the underlying transport if available.
        """
        data = self.conn.data_to_send()
        if data and self.transport:
            self.transport.write(data)

    async def send_with_flow(self, data: bytes, stream_id: int, end: bool = False) -> None:
        """Sends data with flow control.

        Breaks the data into chunks based on the flow control window and sends them
        while respecting the HTTP/2 flow control limits.

        Args:
            data (bytes): The data to send.
            stream_id (int): The ID of the stream to send data on.
            end (bool, optional): Whether to end the stream after sending. Defaults to False.

        Raises:
            StreamClosedError: If the stream is already closed.
            ProtocolError: If an HTTP/2 protocol error occurs.
        """
        idx = 0
        while idx < len(data):
            win = self.conn.local_flow_control_window(stream_id)
            size = min(win, len(data) - idx, self.conn.max_outbound_frame_size)
            if size <= 0:
                fut = asyncio.get_event_loop().create_future()
                self.flow_futures[stream_id] = fut
                await asyncio.wait_for(fut, timeout=IO_TIMEOUT)
                continue
            chunk = data[idx: idx + size]
            try:
                self.conn.send_data(stream_id, chunk, end_stream=(end and idx + size == len(data)))
            except (StreamClosedError, ProtocolError):
                self.conn.end_stream(stream_id)
                self.flush()
                return
            self.flush()
            idx += size

    async def _handle(self, req: Request, stream_id: int) -> None:
        """Handles an incoming gRPC request.

        Processes the request using the handler, sends response headers, payload,
        and trailers over the HTTP/2 stream.

        Args:
            req (Request): The gRPC request to handle.
            stream_id (int): The ID of the stream for the response.
        """
        try:
            resp: Response = await asyncio.wait_for(self.handler(req), timeout=IO_TIMEOUT)
        except Exception as e:
            trailers = [(b'grpc-status', b'13'), (b'grpc-message', str(e).encode())]
            try:
                self.conn.send_headers(stream_id, trailers, end_stream=True)
                self.flush()
            except (StreamClosedError, ProtocolError):
                pass
            return

        _headers = [
            (':status', '200'),
            ('content-type', 'application/grpc'),
            ('te', 'trailers'),
        ] + list(resp.metadata.items())
        try:
            self.conn.send_headers(stream_id, _headers)
            self.flush()

            if isinstance(resp.payload, AsyncIterator):
                async for msg in resp.payload:
                    await req.stream.send(msg)
            else:
                await req.stream.send(resp.payload)

            grpc_status = getattr(resp, 'status', '0')
            grpc_message = getattr(resp, 'message', '')
            trailers = [(b'grpc-status', str(grpc_status).encode()),
                        (b'grpc-message', grpc_message.encode())]
            self.conn.send_headers(stream_id, trailers, end_stream=True)
            self.flush()
        except (StreamClosedError, ProtocolError):
            pass  # If the stream is already closed


class GRPCServer(TransportServer):
    """A gRPC server implementation using HTTP/2.

    Hosts a gRPC service over a specified host and port, supporting SSL and concurrent streams.

    Attributes:
        host (str): The server host address.
        port (int): The server port.
        ssl_context (ssl.SSLContext | None): The SSL context for secure connections.
        handler (Handler | None): The application handler for processing requests.
        server (asyncio.base_events.Server | None): The asyncio server instance.
        config (H2Configuration): The HTTP/2 configuration.
        max_streams (int): The maximum number of concurrent streams.
    """

    def __init__(
            self,
            host: str = '127.0.0.1',
            port: int = 50051,
            ssl_context: ssl.SSLContext | None = None,
            max_streams: int = 100
    ) -> None:
        """Initializes the GRPCServer.

        Args:
            host (str, optional): The server host address. Defaults to '127.0.0.1'.
            port (int, optional): The server port. Default is 50051.
            ssl_context (ssl.SSLContext | None, optional): The SSL context for secure connections. Defaults to None.
            max_streams (int, optional): The maximum number of concurrent streams. Defaults to 100.

        Raises:
            ValueError: If ssl_context is invalid or max_streams is non-positive.
        """
        if ssl_context and not isinstance(ssl_context, ssl.SSLContext):
            raise ValueError("ssl_context must be an instance of ssl.SSLContext")
        if max_streams <= 0:
            raise ValueError("max_streams must be positive")
        self.host, self.port = host, port
        self.ssl_context = ssl_context
        self.handler: Handler | None = None
        self.server: asyncio.base_events.Server | None = None
        self.config = H2Configuration(client_side=False, header_encoding='utf-8')
        self.max_streams = max_streams

    async def start(self):
        """Starts the gRPC server.

        Creates an asyncio server that listens for incoming connections and uses
        the H2GRPCProtocol to handle them.

        Raises:
            OSError: If the server fails to bind to the host/port.
            RuntimeError: If handler is not set.
        """
        if self.handler is None:
            raise RuntimeError("Handler must be set before starting the server")
        loop = asyncio.get_running_loop()
        self.server = await loop.create_server(
            lambda: H2GRPCProtocol(self.handler, self.config, self.max_streams),
            self.host, self.port, ssl=self.ssl_context
        )

    async def serve(self, handler: Handler):
        """Sets the handler for processing gRPC requests.

        Args:
            handler (Handler): The application handler for processing requests.
        """
        self.handler = handler

    async def stop(self):
        """Stops the gRPC server.

        Closes the server and waits for all connections to terminate.
        """
        if self.server:
            self.server.close()
            await self.server.wait_closed()


class GRPCClient(TransportClient):
    """A gRPC client implementation (stub).

    This class is a placeholder and not yet implemented.
    """

    def __init__(self):
        """Initializes the GRPCClient.

        Raises:
            NotImplementedError: Always raised as the client is not implemented.
        """
        raise NotImplementedError("GRPCClient is not implemented yet.")


class GRPC(Transport):
    """A gRPC transport implementation for creating servers and clients.

    Provides factory methods for creating gRPC servers and clients with shared configuration.

    Attributes:
        host (str): The host address for the transport.
        port (int): The port for the transport.
        ssl_context (ssl.SSLContext | None): The SSL context for secure connections.
        max_streams (int): The maximum number of concurrent streams.
    """

    def __init__(
            self,
            host: str = '127.0.0.1',
            port: int = 50051,
            ssl_context: ssl.SSLContext | None = None,
            max_streams: int = 100
    ):
        """Initializes the GRPC transport.

        Args:
            host (str, optional): The host address. Defaults to '127.0.0.1'.
            port (int, optional): The port. Default is 50051.
            ssl_context (ssl.SSLContext | None, optional): The SSL context for secure connections. Defaults to None.
            max_streams (int, optional): The maximum number of concurrent streams. Defaults to 100.

        Raises:
            ValueError: If ssl_context is invalid or max_streams is non-positive.
        """
        if ssl_context and not isinstance(ssl_context, ssl.SSLContext):
            raise ValueError("ssl_context must be an instance of ssl.SSLContext")
        if max_streams <= 0:
            raise ValueError("max_streams must be positive")
        self.host, self.port = host, port
        self.ssl_context = ssl_context
        self.max_streams = max_streams

    def get_server(self) -> GRPCServer:
        """Creates a gRPC server instance.

        Returns:
            GRPCServer: A configured gRPC server instance.
        """
        return GRPCServer(self.host, self.port, self.ssl_context, self.max_streams)

    def get_client(self) -> GRPCClient:
        """Creates a gRPC client instance.

        Returns:
            GRPCClient: A gRPC client instance (currently a stub).
        """
        return GRPCClient()
    