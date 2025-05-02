import asyncio
import ssl
from typing import AsyncIterator, Dict
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import RequestReceived, DataReceived, StreamEnded
from h2.settings import SettingCodes

from microapi.transport.base import Transport, TransportServer, TransportClient, Handler, Request, Response, Stream


def _pack_message(message: bytes) -> bytes:
    # gRPC frame: 1-byte flag + 4-byte length + payload
    return b'\x00' + len(message).to_bytes(4, 'big') + message


class H2Stream(Stream):
    def __init__(self, conn: H2Connection, writer: asyncio.StreamWriter, stream_id: int):
        self.conn = conn
        self.writer = writer
        self.stream_id = stream_id
        self._recv_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def send(self, message: str) -> None:
        frame = _pack_message(message.encode())
        self.conn.send_data(self.stream_id, frame)
        self.writer.write(self.conn.data_to_send())
        await self.writer.drain()

    async def recv(self) -> str:
        chunk = await self._recv_queue.get()
        if chunk is None:
            raise EOFError
        return chunk.decode()

    async def close(self) -> None:
        self.conn.end_stream(self.stream_id)
        self.writer.write(self.conn.data_to_send())
        await self.writer.drain()


class gRPCServer(TransportServer):
    def __init__(
        self,
        host: str = '127.0.0.1',
        port: int = 50051,
        ssl_context: ssl.SSLContext | None = None,
        max_concurrent_streams: int = 100,
    ):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.config = H2Configuration(client_side=False, header_encoding='utf-8')
        self.max_concurrent_streams = max_concurrent_streams
        self.server: asyncio.AbstractServer | None = None
        self._handler: Handler | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self._handle_connection,
            host=self.host,
            port=self.port,
            ssl=self.ssl_context,
        )

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def serve(self, handler: Handler) -> None:
        self._handler = handler

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        conn = H2Connection(config=self.config)
        conn.initiate_connection()
        conn.update_settings({SettingCodes.MAX_CONCURRENT_STREAMS: self.max_concurrent_streams})
        writer.write(conn.data_to_send())
        await writer.drain()

        streams: Dict[int, H2Stream] = {}

        while not reader.at_eof():
            data = await reader.read(65535)
            if not data:
                break

            for event in conn.receive_data(data):
                if isinstance(event, RequestReceived):
                    sid = event.stream_id
                    headers = {k: v for k, v in event.headers}
                    path = headers[':path']
                    svc, mtd = path.lstrip('/').split('/', 1)
                    metadata = {
                        k: v
                        for k, v in event.headers
                        if not k.startswith(':')
                    }
                    h2s = H2Stream(conn, writer, sid)
                    streams[sid] = h2s
                    req = Request(
                        service=svc,
                        method=mtd,
                        payload=[],
                        metadata=metadata,
                        stream=h2s,
                    )
                    asyncio.create_task(self._respond(req))

                elif isinstance(event, DataReceived):
                    sid = event.stream_id
                    chunk = event.data
                    streams[sid]._recv_queue.put_nowait(chunk)
                    conn.acknowledge_received_data(event.flow_controlled_length, sid)

                elif isinstance(event, StreamEnded):
                    sid = event.stream_id
                    streams[sid]._recv_queue.put_nowait(None)

            writer.write(conn.data_to_send())
            await writer.drain()

    async def _respond(self, req: Request) -> None:
        assert self._handler is not None
        resp: Response = await self._handler(req)
        conn = req.stream.conn
        writer = req.stream.writer
        sid = req.stream.stream_id

        # заголовки ответа
        headers = [
            (':status', '200'),
            ('content-type', 'application/grpc'),
            ('te', 'trailers'),
        ] + list(resp.metadata.items())
        conn.send_headers(sid, headers)
        writer.write(conn.data_to_send())
        await writer.drain()

        # тело (sync или async)
        if isinstance(resp.payload, AsyncIterator):
            async for msg in resp.payload:
                await req.stream.send(msg)
        else:
            await req.stream.send(resp.payload)

        # трейлеры grpc-status
        trailers = [
            (b'grpc-status', b'0'),
            (b'grpc-message', b''),
        ]
        conn.send_headers(sid, trailers, end_stream=True)
        writer.write(conn.data_to_send())
        await writer.drain()


class gRPCClient(TransportClient):
    pass


class gRPC(Transport):
    def __init__(
        self,
        host: str = '127.0.0.1',
        port: int = 50051,
        ssl_context: ssl.SSLContext | None = None,
        max_concurrent_streams: int = 100,
    ):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_concurrent_streams = max_concurrent_streams

    def get_server(self) -> gRPCServer:
        return gRPCServer(
            host=self.host,
            port=self.port,
            ssl_context=self.ssl_context,
            max_concurrent_streams=self.max_concurrent_streams,
        )

    def get_client(self) -> gRPCClient:
        return gRPCClient()
