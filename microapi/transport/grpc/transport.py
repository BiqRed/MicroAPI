"""gRPC transport factory."""

from __future__ import annotations

import ssl

from microapi.transport.base import Transport, TransportClient, TransportServer
from microapi.transport.grpc.client import GRPCClient
from microapi.transport.grpc.server import GRPCServer


class GRPCTransport(Transport):
    """gRPC transport (custom HTTP/2, no ``grpcio`` dependency).

    Example::

        from microapi.transport.grpc import GRPCTransport

        app.run(transport=GRPCTransport(host="0.0.0.0", port=50051))
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        ssl_context: ssl.SSLContext | None = None,
        max_streams: int = 128,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_streams = max_streams

    def create_server(self) -> TransportServer:
        return GRPCServer(
            host=self.host,
            port=self.port,
            ssl_context=self.ssl_context,
            max_streams=self.max_streams,
        )

    def create_client(self) -> TransportClient:
        return GRPCClient(
            host=self.host,
            port=self.port,
            ssl_context=self.ssl_context,
        )
