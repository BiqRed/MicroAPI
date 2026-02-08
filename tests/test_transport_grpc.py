"""Integration tests for the gRPC transport."""

from __future__ import annotations

import asyncio

import pytest

from microapi import Schema, Service
from microapi.routing import Router
from microapi.transport.grpc import GRPCTransport


class Payload(Schema):
    name: str


class Result(Schema):
    greeting: str


@pytest.fixture
async def grpc_setup():
    """Start gRPC server + client, yield, then tear down."""
    svc = Service("greeter")

    @svc.method
    async def hello(payload: Payload) -> Result:
        return Result(greeting=f"Hello, {payload.name}!")

    transport = GRPCTransport(host="127.0.0.1", port=19051)
    router = Router()
    router.register_service(svc)

    server = transport.create_server()
    await server.start(router)

    client = transport.create_client()
    await client.connect()
    await asyncio.sleep(0.05)  # allow h2 handshake

    yield client, server

    await client.close()
    await server.stop()


class TestGRPCTransport:
    @pytest.mark.asyncio
    async def test_unary_request(self, grpc_setup) -> None:
        client, _ = grpc_setup
        result = await client.request("greeter", "hello", {"name": "gRPC"})
        assert result["greeting"] == "Hello, gRPC!"

    @pytest.mark.asyncio
    async def test_multiple_requests(self, grpc_setup) -> None:
        client, _ = grpc_setup
        for i in range(5):
            result = await client.request("greeter", "hello", {"name": f"User{i}"})
            assert result["greeting"] == f"Hello, User{i}!"
