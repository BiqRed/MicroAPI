"""Comprehensive integration tests for MicroAPI.

Covers:
- All three transports: HTTP, WebSocket, gRPC
- All RPC patterns: unary, server streaming, client streaming, bidi streaming
- Middleware execution
- Dependency injection
- Error handling
- Code generation validity
- Edge cases (empty payloads, large payloads, concurrent requests)
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest

from microapi import Depends, Middleware, Schema, Service, types
from microapi.client.base import Connection
from microapi.client.stream import ClientStream, ClientStreaming
from microapi.exceptions import (
    StreamClosedError,
    TransportError,
)
from microapi.generator.python_gen import generate_python_lib
from microapi.protocol import (
    Envelope,
    MessageType,
    MethodType,
    Request,
    Response,
    StatusCode,
)
from microapi.routing import Router
from microapi.serialization import deserialize, serialize
from microapi.transport.grpc import GRPCTransport
from microapi.transport.http import HTTPTransport
from microapi.transport.websocket import WebSocketTransport
from microapi.types import Stream

# ---------------------------------------------------------------------------
# Shared schemas and services used across multiple tests
# ---------------------------------------------------------------------------


class UserPayload(Schema):
    name: str
    age: int = 0


class UserResult(Schema):
    greeting: str
    name: str


class NumberPayload(Schema):
    value: int


class NumberResult(Schema):
    result: int


class ChatMessage(Schema):
    text: str


class ChatResponse(Schema):
    reply: str


def _build_full_service() -> Service:
    """Build a service with all RPC patterns."""
    svc = Service("test_service")

    @svc.method
    async def greet(payload: UserPayload) -> UserResult:
        return UserResult(greeting=f"Hello, {payload.name}!", name=payload.name)

    @svc.method
    async def echo(payload: UserPayload) -> UserPayload:
        return payload

    @svc.method
    async def no_input() -> UserResult:
        return UserResult(greeting="No input!", name="anonymous")

    @svc.method
    async def count_up(payload: NumberPayload) -> types.Streaming[NumberResult]:
        for i in range(payload.value):
            yield NumberResult(result=i)

    @svc.method
    async def sum_stream(stream: Stream[NumberPayload]) -> NumberResult:
        total = 0
        async for item in stream:
            total += item.value
        return NumberResult(result=total)

    @svc.method
    async def chat(stream: Stream[ChatMessage]) -> types.Streaming[ChatResponse]:
        async for msg in stream:
            yield ChatResponse(reply=f"Echo: {msg.text}")

    return svc


def _build_router_with_middleware() -> Router:
    """Build a router with middleware and dependencies."""
    svc = Service("mw_service")

    class AddHeaderMiddleware(Middleware):
        async def __call__(self, request: Request, call_next: Any) -> Response:
            request.metadata["middleware_applied"] = "true"
            return await call_next(request)

    class LoggingMiddleware(Middleware):
        async def __call__(self, request: Request, call_next: Any) -> Response:
            request.metadata["logged"] = "yes"
            response = await call_next(request)
            return response

    async def get_config(req: Request) -> dict[str, str]:
        return {"version": "1.0", "has_middleware": req.metadata.get("middleware_applied", "false")}

    @svc.method
    async def with_deps(payload: UserPayload, config: dict[str, str] = Depends(get_config)) -> UserResult:  # noqa: B008
        return UserResult(
            greeting=f"Hello, {payload.name}! Config v{config['version']} mw={config['has_middleware']}",
            name=payload.name,
        )

    router = Router()
    router.register_service(svc)
    router.add_middleware(AddHeaderMiddleware())
    router.add_middleware(LoggingMiddleware())
    return router


# ===========================================================================
# HTTP Transport Tests
# ===========================================================================


@pytest.fixture
async def http_full_setup():
    """HTTP transport with all RPC patterns."""
    svc = _build_full_service()
    transport = HTTPTransport(host="127.0.0.1", port=19081)
    router = Router()
    router.register_service(svc)

    server = transport.create_server()
    await server.start(router)
    client = transport.create_client()
    await client.connect()

    yield client, server

    await client.close()
    await server.stop()


class TestHTTPIntegration:
    @pytest.mark.asyncio
    async def test_unary_greet(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        result = await client.request("test_service", "greet", {"name": "Alice", "age": 30})
        assert result["greeting"] == "Hello, Alice!"
        assert result["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_unary_echo(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        result = await client.request("test_service", "echo", {"name": "Bob", "age": 25})
        assert result["name"] == "Bob"
        assert result["age"] == 25

    @pytest.mark.asyncio
    async def test_no_input_method(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        result = await client.request("test_service", "no_input", {})
        assert result["greeting"] == "No input!"

    @pytest.mark.asyncio
    async def test_server_streaming(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        items = []
        async for item in client.request_stream("test_service", "count_up", {"value": 5}):
            items.append(item)
        assert len(items) == 5
        assert items[0]["result"] == 0
        assert items[4]["result"] == 4

    @pytest.mark.asyncio
    async def test_server_streaming_zero_items(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        items = []
        async for item in client.request_stream("test_service", "count_up", {"value": 0}):
            items.append(item)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_client_streaming(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        # Client streaming: send list of payloads
        payload = [{"value": 1}, {"value": 2}, {"value": 3}]
        result = await client.request("test_service", "sum_stream", payload)
        assert result["result"] == 6

    @pytest.mark.asyncio
    async def test_error_service_not_found(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        with pytest.raises(TransportError, match="404"):
            await client.request("nonexistent", "method")

    @pytest.mark.asyncio
    async def test_error_method_not_found(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        with pytest.raises(TransportError, match="404"):
            await client.request("test_service", "nonexistent")

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        tasks = [client.request("test_service", "greet", {"name": f"User{i}", "age": i}) for i in range(10)]
        results = await asyncio.gather(*tasks)
        for i, result in enumerate(results):
            assert result["greeting"] == f"Hello, User{i}!"

    @pytest.mark.asyncio
    async def test_large_payload(self, http_full_setup: Any) -> None:
        client, _ = http_full_setup
        long_name = "x" * 10000
        result = await client.request("test_service", "greet", {"name": long_name, "age": 1})
        assert result["name"] == long_name


# ===========================================================================
# WebSocket Transport Tests
# ===========================================================================


@pytest.fixture
async def ws_full_setup():
    """WebSocket transport with all RPC patterns."""
    svc = _build_full_service()
    transport = WebSocketTransport(host="127.0.0.1", port=19766)
    router = Router()
    router.register_service(svc)

    server = transport.create_server()
    await server.start(router)
    client = transport.create_client()
    await client.connect()

    yield client, server

    await client.close()
    await server.stop()


class TestWebSocketIntegration:
    @pytest.mark.asyncio
    async def test_unary_greet(self, ws_full_setup: Any) -> None:
        client, _ = ws_full_setup
        result = await client.request("test_service", "greet", {"name": "Alice", "age": 30})
        assert result["greeting"] == "Hello, Alice!"

    @pytest.mark.asyncio
    async def test_unary_echo(self, ws_full_setup: Any) -> None:
        client, _ = ws_full_setup
        result = await client.request("test_service", "echo", {"name": "Bob", "age": 25})
        assert result["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_no_input_method(self, ws_full_setup: Any) -> None:
        client, _ = ws_full_setup
        result = await client.request("test_service", "no_input", {})
        assert result["greeting"] == "No input!"

    @pytest.mark.asyncio
    async def test_server_streaming(self, ws_full_setup: Any) -> None:
        client, _ = ws_full_setup
        items = []
        async for item in client.request_stream("test_service", "count_up", {"value": 4}):
            items.append(item)
        assert len(items) == 4
        assert [i["result"] for i in items] == [0, 1, 2, 3]

    @pytest.mark.asyncio
    async def test_server_streaming_zero_items(self, ws_full_setup: Any) -> None:
        client, _ = ws_full_setup
        items = []
        async for item in client.request_stream("test_service", "count_up", {"value": 0}):
            items.append(item)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, ws_full_setup: Any) -> None:
        client, _ = ws_full_setup
        tasks = [client.request("test_service", "greet", {"name": f"User{i}", "age": i}) for i in range(10)]
        results = await asyncio.gather(*tasks)
        for i, result in enumerate(results):
            assert result["greeting"] == f"Hello, User{i}!"

    @pytest.mark.asyncio
    async def test_error_service_not_found(self, ws_full_setup: Any) -> None:
        client, _ = ws_full_setup
        with pytest.raises(TransportError):
            await client.request("nonexistent", "method")


# ===========================================================================
# gRPC Transport Tests
# ===========================================================================


@pytest.fixture
async def grpc_full_setup():
    """gRPC transport with full service."""
    svc = _build_full_service()
    transport = GRPCTransport(host="127.0.0.1", port=19052)
    router = Router()
    router.register_service(svc)

    server = transport.create_server()
    await server.start(router)
    client = transport.create_client()
    await client.connect()
    await asyncio.sleep(0.05)

    yield client, server

    await client.close()
    await server.stop()


class TestGRPCIntegration:
    @pytest.mark.asyncio
    async def test_unary_greet(self, grpc_full_setup: Any) -> None:
        client, _ = grpc_full_setup
        result = await client.request("test_service", "greet", {"name": "Alice", "age": 30})
        assert result["greeting"] == "Hello, Alice!"

    @pytest.mark.asyncio
    async def test_unary_echo(self, grpc_full_setup: Any) -> None:
        client, _ = grpc_full_setup
        result = await client.request("test_service", "echo", {"name": "Bob", "age": 25})
        assert result["name"] == "Bob"
        assert result["age"] == 25

    @pytest.mark.asyncio
    async def test_no_input_method(self, grpc_full_setup: Any) -> None:
        client, _ = grpc_full_setup
        result = await client.request("test_service", "no_input", {})
        assert result["greeting"] == "No input!"

    @pytest.mark.asyncio
    async def test_multiple_sequential_requests(self, grpc_full_setup: Any) -> None:
        client, _ = grpc_full_setup
        for i in range(5):
            result = await client.request("test_service", "greet", {"name": f"User{i}", "age": i})
            assert result["greeting"] == f"Hello, User{i}!"

    @pytest.mark.asyncio
    async def test_server_streaming_via_grpc(self, grpc_full_setup: Any) -> None:
        """Test gRPC streaming response via request_stream."""
        client, _ = grpc_full_setup
        items = []
        async for item in client.request_stream("test_service", "count_up", {"value": 3}):
            items.append(item)
        assert len(items) == 3
        assert [i["result"] for i in items] == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_large_payload(self, grpc_full_setup: Any) -> None:
        client, _ = grpc_full_setup
        long_name = "a" * 10000
        result = await client.request("test_service", "greet", {"name": long_name, "age": 1})
        assert result["name"] == long_name


# ===========================================================================
# Middleware + Dependency Injection Tests
# ===========================================================================


class TestMiddlewareAndDeps:
    @pytest.mark.asyncio
    async def test_middleware_and_deps_via_router(self) -> None:
        """Verify middleware runs and dependencies see the middleware-modified metadata."""
        router = _build_router_with_middleware()
        request = Request(
            service="mw_service",
            method="with_deps",
            payload={"name": "Alice", "age": 25},
        )
        response = await router.handle_request(request)
        assert response.status_code == StatusCode.OK
        assert response.payload is not None
        assert response.payload["greeting"] == "Hello, Alice! Config v1.0 mw=true"

    @pytest.mark.asyncio
    async def test_middleware_order_preserved(self) -> None:
        """Ensure middlewares execute in registration order."""
        order: list[str] = []

        class MW1(Middleware):
            async def __call__(self, request: Request, call_next: Any) -> Response:
                order.append("mw1_before")
                resp = await call_next(request)
                order.append("mw1_after")
                return resp

        class MW2(Middleware):
            async def __call__(self, request: Request, call_next: Any) -> Response:
                order.append("mw2_before")
                resp = await call_next(request)
                order.append("mw2_after")
                return resp

        svc = Service("order_svc")

        @svc.method
        async def noop(payload: UserPayload) -> UserResult:
            order.append("handler")
            return UserResult(greeting="ok", name=payload.name)

        router = Router()
        router.register_service(svc)
        router.add_middleware(MW1())
        router.add_middleware(MW2())

        request = Request(service="order_svc", method="noop", payload={"name": "test", "age": 0})
        await router.handle_request(request)

        assert order == ["mw1_before", "mw2_before", "handler", "mw2_after", "mw1_after"]

    @pytest.mark.asyncio
    async def test_middleware_short_circuit(self) -> None:
        """Test that middleware can short-circuit the request."""

        class AuthMiddleware(Middleware):
            async def __call__(self, request: Request, call_next: Any) -> Response:
                if request.metadata.get("auth") != "valid":
                    return Response(error="Unauthorized", status_code=StatusCode.UNAUTHENTICATED)
                return await call_next(request)

        svc = Service("auth_svc")

        @svc.method
        async def protected(payload: UserPayload) -> UserResult:
            return UserResult(greeting="Secret!", name=payload.name)

        router = Router()
        router.register_service(svc)
        router.add_middleware(AuthMiddleware())

        # Without auth
        req1 = Request(service="auth_svc", method="protected", payload={"name": "Alice", "age": 0})
        resp1 = await router.handle_request(req1)
        assert resp1.error == "Unauthorized"
        assert resp1.status_code == StatusCode.UNAUTHENTICATED

        # With auth
        req2 = Request(
            service="auth_svc",
            method="protected",
            payload={"name": "Alice", "age": 0},
            metadata={"auth": "valid"},
        )
        resp2 = await router.handle_request(req2)
        assert resp2.status_code == StatusCode.OK
        assert resp2.payload is not None
        assert resp2.payload["greeting"] == "Secret!"


# ===========================================================================
# Stream Tests (unit-level)
# ===========================================================================


class TestStreamEdgeCases:
    @pytest.mark.asyncio
    async def test_double_close_is_safe(self) -> None:
        """Closing a stream twice should not raise or duplicate sentinels."""
        stream: Stream[int] = Stream()
        await stream._feed(1)
        await stream._close()
        await stream._close()  # Should not raise
        assert stream.closed

        # Should get item then StopAsyncIteration
        items = []
        async for item in stream:
            items.append(item)
        assert items == [1]

    @pytest.mark.asyncio
    async def test_feed_after_close_raises(self) -> None:
        stream: Stream[int] = Stream()
        await stream._close()
        with pytest.raises(StreamClosedError):
            await stream._feed(42)

    @pytest.mark.asyncio
    async def test_large_stream(self) -> None:
        """Test streaming a large number of items."""
        stream: Stream[int] = Stream()
        n = 1000

        async def producer() -> None:
            for i in range(n):
                await stream._feed(i)
            await stream._close()

        items: list[int] = []

        async def consumer() -> None:
            async for item in stream:
                items.append(item)

        await asyncio.gather(producer(), consumer())
        assert len(items) == n
        assert items == list(range(n))

    @pytest.mark.asyncio
    async def test_concurrent_producers(self) -> None:
        """Multiple producers feeding the same stream."""
        stream: Stream[int] = Stream()

        async def producer(start: int, count: int) -> None:
            for i in range(start, start + count):
                await stream._feed(i)

        items: list[int] = []

        async def consumer() -> None:
            async for item in stream:
                items.append(item)

        await asyncio.gather(producer(0, 50), producer(50, 50))
        await stream._close()

        # Collect remaining items
        async for item in stream:
            items.append(item)

        assert len(items) == 100


# ===========================================================================
# Code Generation Tests
# ===========================================================================


class TestCodeGeneration:
    def test_generates_valid_python(self) -> None:
        """Generated code should be syntactically valid Python."""
        svc = _build_full_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "lib"
            generate_python_lib({"test_service": svc}, output_dir)

            # Check all expected files exist
            assert (output_dir / "__init__.py").exists()
            assert (output_dir / "types.py").exists()
            assert (output_dir / "test_service.py").exists()

            # Verify they're valid Python by compiling them
            for pyfile in output_dir.glob("*.py"):
                source = pyfile.read_text()
                compile(source, str(pyfile), "exec")  # Raises SyntaxError if invalid

    def test_types_file_has_schemas(self) -> None:
        svc = _build_full_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "lib"
            generate_python_lib({"test_service": svc}, output_dir)

            types_content = (output_dir / "types.py").read_text()
            assert "class UserPayload" in types_content
            assert "class UserResult" in types_content
            assert "class NumberPayload" in types_content
            assert "class NumberResult" in types_content
            assert "class ChatMessage" in types_content
            assert "class ChatResponse" in types_content

    def test_service_module_has_all_methods(self) -> None:
        svc = _build_full_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "lib"
            generate_python_lib({"test_service": svc}, output_dir)

            svc_content = (output_dir / "test_service.py").read_text()
            assert "async def greet" in svc_content
            assert "async def echo" in svc_content
            assert "async def count_up" in svc_content
            # Client streaming generates a class (uses the function name as-is)
            assert "class sum_stream" in svc_content
            # Bidi streaming generates a class
            assert "class chat" in svc_content

    def test_generated_code_has_proper_types(self) -> None:
        svc = _build_full_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "lib"
            generate_python_lib({"test_service": svc}, output_dir)

            svc_content = (output_dir / "test_service.py").read_text()
            # Unary: returns typed result
            assert "-> UserResult:" in svc_content
            assert "-> UserPayload:" in svc_content
            # Server streaming: returns AsyncIterator
            assert "AsyncIterator[NumberResult]" in svc_content

    def test_protobuf_generation(self) -> None:
        from microapi.generator.protobuf_gen import generate_proto_files

        svc = _build_full_service()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "protos"
            generate_proto_files({"test_service": svc}, output_dir)

            proto_file = output_dir / "test_service.proto"
            assert proto_file.exists()

            content = proto_file.read_text()
            assert 'syntax = "proto3"' in content
            assert "message UserPayload" in content
            assert "service Test_serviceService" in content


# ===========================================================================
# Serialization Edge Cases
# ===========================================================================


class TestSerializationEdgeCases:
    def test_serialize_none_field(self) -> None:
        data = {"key": None, "other": "value"}
        result = deserialize(serialize(data))
        assert result["key"] is None
        assert result["other"] == "value"

    def test_serialize_nested(self) -> None:
        data = {"outer": {"inner": [1, 2, 3], "nested": {"deep": True}}}
        result = deserialize(serialize(data))
        assert result == data

    def test_serialize_unicode(self) -> None:
        data = {"text": "Привет мир! 你好世界 🌍"}
        result = deserialize(serialize(data))
        assert result["text"] == data["text"]

    def test_serialize_empty(self) -> None:
        result = deserialize(serialize({}))
        assert result == {}

    def test_serialize_list(self) -> None:
        data = [1, 2, 3]
        result = deserialize(serialize(data))
        assert result == data


# ===========================================================================
# Protocol Edge Cases
# ===========================================================================


class TestProtocolEdgeCases:
    def test_envelope_roundtrip(self) -> None:
        envelope = Envelope(
            type=MessageType.REQUEST,
            service="test",
            method="method",
            payload={"key": "value"},
            metadata={"auth": "token"},
        )
        data = envelope.to_dict()
        restored = Envelope.from_dict(data)
        assert restored.type == MessageType.REQUEST
        assert restored.service == "test"
        assert restored.method == "method"
        assert restored.payload == {"key": "value"}
        assert restored.metadata["auth"] == "token"

    def test_envelope_id_auto_generated(self) -> None:
        e1 = Envelope(type=MessageType.REQUEST)
        e2 = Envelope(type=MessageType.REQUEST)
        assert e1.id != e2.id
        assert len(e1.id) > 0

    def test_request_id_auto_generated(self) -> None:
        r1 = Request(service="a", method="b")
        r2 = Request(service="a", method="b")
        assert r1.id != r2.id


# ===========================================================================
# Client-side Primitives Tests
# ===========================================================================


class TestClientPrimitives:
    @pytest.mark.asyncio
    async def test_client_stream_buffer_and_end(self) -> None:
        """Test that ClientStream buffers sends and dispatches on end()."""
        sent_data: dict[str, Any] = {}

        class FakeTransport:
            async def request(self, service: str, method: str, payload: Any, **kw: Any) -> dict[str, Any]:
                sent_data["service"] = service
                sent_data["method"] = method
                sent_data["payload"] = payload
                return {"result": sum(p.get("value", 0) for p in payload)}

        stream: ClientStream[Any] = ClientStream(service="svc", method="meth", transport=FakeTransport())
        await stream._send_raw({"value": 1})
        await stream._send_raw({"value": 2})
        await stream._send_raw({"value": 3})
        result = await stream.end()

        assert sent_data["service"] == "svc"
        assert sent_data["method"] == "meth"
        assert len(sent_data["payload"]) == 3
        assert result == {"result": 6}

    @pytest.mark.asyncio
    async def test_client_streaming_iterates(self) -> None:
        """Test ClientStreaming async iteration."""

        async def fake_stream():
            for i in range(3):
                yield {"value": i}

        streaming: ClientStreaming[dict[str, int]] = ClientStreaming(
            stream=fake_stream(),
            model=dict,  # type: ignore[arg-type]
        )
        items = []
        async for item in streaming:
            items.append(item)
        assert len(items) == 3
        assert items == [{"value": 0}, {"value": 1}, {"value": 2}]

    @pytest.mark.asyncio
    async def test_connection_context_manager(self) -> None:
        """Test Connection as async context manager."""

        class FakeTransport:
            connected = False

            async def connect(self) -> None:
                self.connected = True

            async def close(self) -> None:
                self.connected = False

        ft = FakeTransport()
        conn = Connection(ft)

        async with conn as c:
            assert c is conn
            assert ft.connected
            assert Connection.get_current() is conn

        assert not ft.connected
        # After exit, current connection should be cleared
        with pytest.raises(RuntimeError, match="No active MicroAPI connection"):
            Connection.get_current()


# ===========================================================================
# Routing Edge Cases
# ===========================================================================


class TestRoutingEdgeCases:
    @pytest.mark.asyncio
    async def test_validation_error_returns_invalid_argument(self) -> None:
        """Invalid payload should return INVALID_ARGUMENT."""
        svc = Service("val_svc")

        @svc.method
        async def typed_method(payload: UserPayload) -> UserResult:
            return UserResult(greeting="ok", name=payload.name)

        router = Router()
        router.register_service(svc)

        # Missing required 'name' field
        request = Request(service="val_svc", method="typed_method", payload={"wrong_field": "oops"})
        response = await router.handle_request(request)
        assert response.status_code == StatusCode.INVALID_ARGUMENT

    @pytest.mark.asyncio
    async def test_handler_exception_returns_internal_error(self) -> None:
        """Exceptions in handlers should return INTERNAL."""
        svc = Service("err_svc")

        @svc.method
        async def explode(payload: UserPayload) -> UserResult:
            raise ValueError("Boom!")

        router = Router()
        router.register_service(svc)

        request = Request(service="err_svc", method="explode", payload={"name": "test", "age": 0})
        response = await router.handle_request(request)
        assert response.status_code == StatusCode.INTERNAL
        assert "Boom!" in (response.error or "")

    @pytest.mark.asyncio
    async def test_none_return_value(self) -> None:
        """Methods returning None should work."""
        svc = Service("none_svc")

        @svc.method
        async def void_method(payload: UserPayload) -> None:
            pass

        router = Router()
        router.register_service(svc)

        request = Request(service="none_svc", method="void_method", payload={"name": "test", "age": 0})
        response = await router.handle_request(request)
        assert response.status_code == StatusCode.OK


# ===========================================================================
# Service Registration Tests
# ===========================================================================


class TestServiceRegistration:
    def test_method_type_detection(self) -> None:
        svc = _build_full_service()
        assert svc.methods["greet"].method_type == MethodType.UNARY
        assert svc.methods["count_up"].method_type == MethodType.SERVER_STREAMING
        assert svc.methods["sum_stream"].method_type == MethodType.CLIENT_STREAMING
        assert svc.methods["chat"].method_type == MethodType.BIDI_STREAMING

    def test_input_type_detection(self) -> None:
        svc = _build_full_service()
        assert svc.methods["greet"].input_type is UserPayload
        assert svc.methods["count_up"].input_type is NumberPayload

    def test_output_type_detection(self) -> None:
        svc = _build_full_service()
        assert svc.methods["greet"].output_type is UserResult
        assert svc.methods["count_up"].output_type is NumberResult
        assert svc.methods["sum_stream"].output_type is NumberResult

    def test_stream_input_type_detection(self) -> None:
        svc = _build_full_service()
        assert svc.methods["sum_stream"].stream_input_type is NumberPayload
        assert svc.methods["chat"].stream_input_type is ChatMessage
