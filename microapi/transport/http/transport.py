"""HTTP transport factory."""

from __future__ import annotations

from microapi.transport.base import Transport, TransportClient, TransportServer
from microapi.transport.http.client import HTTPClient
from microapi.transport.http.server import HTTPServer


class HTTPTransport(Transport):
    """HTTP transport using aiohttp.

    Example::

        from microapi.transport.http import HTTPTransport

        app.run(transport=HTTPTransport(host="0.0.0.0", port=8080))
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        self.host = host
        self.port = port

    def create_server(self) -> TransportServer:
        return HTTPServer(host=self.host, port=self.port)

    def create_client(self) -> TransportClient:
        return HTTPClient(base_url=f"http://{self.host}:{self.port}")
