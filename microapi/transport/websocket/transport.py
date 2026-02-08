"""WebSocket transport factory."""

from __future__ import annotations

from microapi.transport.base import Transport, TransportClient, TransportServer
from microapi.transport.websocket.client import WebSocketClient
from microapi.transport.websocket.server import WebSocketServer


class WebSocketTransport(Transport):
    """WebSocket transport.

    Example::

        from microapi.transport.websocket import WebSocketTransport

        app.run(transport=WebSocketTransport(host="0.0.0.0", port=8765))
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port

    def create_server(self) -> TransportServer:
        return WebSocketServer(host=self.host, port=self.port)

    def create_client(self) -> TransportClient:
        return WebSocketClient(url=f"ws://{self.host}:{self.port}")
