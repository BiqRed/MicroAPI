"""Tests for microapi.routing."""

from __future__ import annotations

import pytest

from microapi import Schema, Service, types
from microapi.middleware import Middleware
from microapi.protocol import MethodType, Request, StatusCode
from microapi.routing import Router


class Payload(Schema):
    name: str


class Result(Schema):
    greeting: str


class TestRouter:
    @pytest.fixture
    def router_with_service(self) -> Router:
        svc = Service("greeter")

        @svc.method
        async def hello(payload: Payload) -> Result:
            return Result(greeting=f"Hello, {payload.name}!")

        @svc.method
        async def stream_hello(payload: Payload) -> types.Streaming[Result]:
            for i in range(3):
                yield Result(greeting=f"Hi #{i}, {payload.name}!")

        router = Router()
        router.register_service(svc)
        return router

    @pytest.mark.asyncio
    async def test_unary_dispatch(self, router_with_service: Router) -> None:
        req = Request(service="greeter", method="hello", payload={"name": "World"})
        resp = await router_with_service.handle_request(req)

        assert resp.status_code == StatusCode.OK
        assert resp.payload["greeting"] == "Hello, World!"

    @pytest.mark.asyncio
    async def test_server_streaming_dispatch(self, router_with_service: Router) -> None:
        req = Request(service="greeter", method="stream_hello", payload={"name": "Test"})
        resp = await router_with_service.handle_request(req)

        assert resp.is_streaming
        items = []
        async for item in resp.payload:
            from microapi.serialization import to_dict

            items.append(to_dict(item))
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_service_not_found(self, router_with_service: Router) -> None:
        req = Request(service="nonexistent", method="foo")
        resp = await router_with_service.handle_request(req)
        assert resp.status_code == StatusCode.NOT_FOUND

    @pytest.mark.asyncio
    async def test_method_not_found(self, router_with_service: Router) -> None:
        req = Request(service="greeter", method="nonexistent")
        resp = await router_with_service.handle_request(req)
        assert resp.status_code == StatusCode.NOT_FOUND

    def test_register_duplicate_service(self) -> None:
        svc = Service("dup")
        router = Router()
        router.register_service(svc)
        with pytest.raises(ValueError, match="already registered"):
            router.register_service(svc)

    def test_get_method_type(self, router_with_service: Router) -> None:
        assert router_with_service.get_method_type("greeter", "hello") == MethodType.UNARY
        assert router_with_service.get_method_type("greeter", "stream_hello") == MethodType.SERVER_STREAMING

    @pytest.mark.asyncio
    async def test_middleware_in_router(self) -> None:
        svc = Service("mw_test")

        @svc.method
        async def hello(payload: Payload) -> Result:
            return Result(greeting=f"Hello, {payload.name}!")

        class AddHeaderMiddleware(Middleware):
            async def __call__(self, request: Request, call_next):
                resp = await call_next(request)
                resp.metadata["x-custom"] = "test"
                return resp

        router = Router()
        router.register_service(svc)
        router.add_middleware(AddHeaderMiddleware())

        req = Request(service="mw_test", method="hello", payload={"name": "MW"})
        resp = await router.handle_request(req)

        assert resp.payload["greeting"] == "Hello, MW!"
        assert resp.metadata["x-custom"] == "test"

    @pytest.mark.asyncio
    async def test_client_streaming_dispatch(self) -> None:
        svc = Service("stream_test")

        @svc.method
        async def collect(stream: types.Stream[Payload]) -> Result:
            names = []
            async for item in stream:
                names.append(item.name)
            return Result(greeting=f"Got: {', '.join(names)}")

        router = Router()
        router.register_service(svc)

        # Simulate a client stream
        from microapi.types import Stream

        client_stream: Stream[Payload] = Stream()
        await client_stream._feed(Payload(name="Alice"))
        await client_stream._feed(Payload(name="Bob"))
        await client_stream._close()

        req = Request(service="stream_test", method="collect")
        resp = await router.handle_request(req, client_stream=client_stream)

        assert resp.payload["greeting"] == "Got: Alice, Bob"
