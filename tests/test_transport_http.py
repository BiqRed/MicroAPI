"""Integration tests for the HTTP transport."""

from __future__ import annotations

import pytest

from microapi import Schema, Service, types
from microapi.routing import Router
from microapi.transport.http import HTTPTransport


class Payload(Schema):
    name: str


class Result(Schema):
    greeting: str


@pytest.fixture
async def http_setup():
    """Start HTTP server + client, yield, then tear down."""
    svc = Service("greeter")

    @svc.method
    async def hello(payload: Payload) -> Result:
        return Result(greeting=f"Hello, {payload.name}!")

    @svc.method
    async def stream_hello(payload: Payload) -> types.Streaming[Result]:
        for i in range(3):
            yield Result(greeting=f"Hi #{i}, {payload.name}!")

    transport = HTTPTransport(host="127.0.0.1", port=19080)
    router = Router()
    router.register_service(svc)

    server = transport.create_server()
    await server.start(router)

    client = transport.create_client()
    await client.connect()

    yield client, server

    await client.close()
    await server.stop()


class TestHTTPTransport:
    @pytest.mark.asyncio
    async def test_unary_request(self, http_setup) -> None:
        client, _ = http_setup
        result = await client.request("greeter", "hello", {"name": "HTTP"})
        assert result["greeting"] == "Hello, HTTP!"

    @pytest.mark.asyncio
    async def test_server_streaming(self, http_setup) -> None:
        client, _ = http_setup
        items = []
        async for item in client.request_stream("greeter", "stream_hello", {"name": "Stream"}):
            items.append(item)
        assert len(items) == 3
        assert items[0]["greeting"] == "Hi #0, Stream!"

    @pytest.mark.asyncio
    async def test_not_found(self, http_setup) -> None:
        from microapi.exceptions import TransportError

        client, _ = http_setup
        with pytest.raises(TransportError, match="404"):
            await client.request("nonexistent", "method")
