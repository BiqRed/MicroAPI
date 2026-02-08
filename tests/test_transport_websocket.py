"""Integration tests for the WebSocket transport."""

from __future__ import annotations

import pytest

from microapi import Schema, Service, types
from microapi.routing import Router
from microapi.transport.websocket import WebSocketTransport


class Payload(Schema):
    name: str


class Result(Schema):
    greeting: str


@pytest.fixture
async def ws_setup():
    """Start WebSocket server + client, yield, then tear down."""
    svc = Service("greeter")

    @svc.method
    async def hello(payload: Payload) -> Result:
        return Result(greeting=f"Hello, {payload.name}!")

    @svc.method
    async def stream_hello(payload: Payload) -> types.Streaming[Result]:
        for i in range(3):
            yield Result(greeting=f"Hi #{i}, {payload.name}!")

    transport = WebSocketTransport(host="127.0.0.1", port=19765)
    router = Router()
    router.register_service(svc)

    server = transport.create_server()
    await server.start(router)

    client = transport.create_client()
    await client.connect()

    yield client, server

    await client.close()
    await server.stop()


class TestWebSocketTransport:
    @pytest.mark.asyncio
    async def test_unary_request(self, ws_setup) -> None:
        client, _ = ws_setup
        result = await client.request("greeter", "hello", {"name": "WS"})
        assert result["greeting"] == "Hello, WS!"

    @pytest.mark.asyncio
    async def test_server_streaming(self, ws_setup) -> None:
        client, _ = ws_setup
        items = []
        async for item in client.request_stream("greeter", "stream_hello", {"name": "WS"}):
            items.append(item)
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self, ws_setup) -> None:
        import asyncio

        client, _ = ws_setup
        tasks = [client.request("greeter", "hello", {"name": f"User{i}"}) for i in range(5)]
        results = await asyncio.gather(*tasks)
        for i, result in enumerate(results):
            assert result["greeting"] == f"Hello, User{i}!"
