"""Tests for microapi.middleware."""

from __future__ import annotations

import pytest

from microapi.middleware import CallNext, Middleware, MiddlewareChain
from microapi.protocol import Request, Response, StatusCode


class LogMiddleware(Middleware):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, request: Request, call_next: CallNext) -> Response:
        self.calls.append(f"before:{request.method}")
        response = await call_next(request)
        self.calls.append(f"after:{request.method}")
        return response


class ModifyMiddleware(Middleware):
    async def __call__(self, request: Request, call_next: CallNext) -> Response:
        request.metadata["modified"] = "true"
        return await call_next(request)


class ShortCircuitMiddleware(Middleware):
    async def __call__(self, request: Request, call_next: CallNext) -> Response:
        return Response(payload={"short": "circuited"}, status_code=StatusCode.OK)


class TestMiddleware:
    @pytest.mark.asyncio
    async def test_single_middleware(self) -> None:
        log = LogMiddleware()

        async def handler(req: Request) -> Response:
            return Response(payload={"ok": True})

        chain = MiddlewareChain([log], handler)
        resp = await chain(Request(service="s", method="m"))

        assert resp.payload == {"ok": True}
        assert log.calls == ["before:m", "after:m"]

    @pytest.mark.asyncio
    async def test_middleware_order(self) -> None:
        log1 = LogMiddleware()
        log2 = LogMiddleware()

        async def handler(req: Request) -> Response:
            return Response(payload={})

        chain = MiddlewareChain([log1, log2], handler)
        await chain(Request(service="s", method="test"))

        # First middleware runs first
        assert log1.calls == ["before:test", "after:test"]
        assert log2.calls == ["before:test", "after:test"]

    @pytest.mark.asyncio
    async def test_middleware_modifies_request(self) -> None:
        async def handler(req: Request) -> Response:
            return Response(payload={"modified": req.metadata.get("modified", "false")})

        chain = MiddlewareChain([ModifyMiddleware()], handler)
        resp = await chain(Request(service="s", method="m"))

        assert resp.payload["modified"] == "true"

    @pytest.mark.asyncio
    async def test_short_circuit(self) -> None:
        async def handler(req: Request) -> Response:
            return Response(payload={"should_not": "reach"})

        chain = MiddlewareChain([ShortCircuitMiddleware()], handler)
        resp = await chain(Request(service="s", method="m"))

        assert resp.payload == {"short": "circuited"}

    @pytest.mark.asyncio
    async def test_empty_middleware_chain(self) -> None:
        async def handler(req: Request) -> Response:
            return Response(payload={"direct": True})

        chain = MiddlewareChain([], handler)
        resp = await chain(Request(service="s", method="m"))

        assert resp.payload == {"direct": True}
