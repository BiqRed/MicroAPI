"""Tests for microapi.service."""

from __future__ import annotations

from microapi import Depends, Schema, Service, types
from microapi.dependencies import _Depends
from microapi.protocol import MethodType


class Payload(Schema):
    name: str


class Result(Schema):
    greeting: str


class TestServiceRegistration:
    def test_register_unary_method(self) -> None:
        svc = Service("test")

        @svc.method
        async def greet(payload: Payload) -> Result:
            return Result(greeting=f"Hello, {payload.name}")

        assert "greet" in svc.methods
        info = svc.methods["greet"]
        assert info.method_type == MethodType.UNARY
        assert info.input_type is Payload
        assert info.output_type is Result
        assert info.generated_name == "greet"

    def test_register_with_generated_name(self) -> None:
        svc = Service("test")

        @svc.method(generated_name="say_hello")
        async def greet(payload: Payload) -> Result:
            return Result(greeting=f"Hello, {payload.name}")

        info = svc.methods["greet"]
        assert info.generated_name == "say_hello"

    def test_detect_server_streaming(self) -> None:
        svc = Service("test")

        @svc.method
        async def stream_results(payload: Payload) -> types.Streaming[Result]:
            yield Result(greeting="Hello")

        info = svc.methods["stream_results"]
        assert info.method_type == MethodType.SERVER_STREAMING
        assert info.output_type is Result

    def test_detect_client_streaming(self) -> None:
        svc = Service("test")

        @svc.method
        async def collect(stream: types.Stream[Payload]) -> Result:
            count = 0
            async for _ in stream:
                count += 1
            return Result(greeting=f"Got {count}")

        info = svc.methods["collect"]
        assert info.method_type == MethodType.CLIENT_STREAMING
        assert info.stream_input_type is Payload

    def test_detect_bidi_streaming(self) -> None:
        svc = Service("test")

        @svc.method
        async def transform(stream: types.Stream[Payload]) -> types.Streaming[Result]:
            async for item in stream:
                yield Result(greeting=f"Hi {item.name}")

        info = svc.methods["transform"]
        assert info.method_type == MethodType.BIDI_STREAMING
        assert info.stream_input_type is Payload
        assert info.output_type is Result

    def test_dependencies_detected(self) -> None:
        async def get_db():
            return "db_connection"

        svc = Service("test")

        @svc.method
        async def greet(payload: Payload, db: str = Depends(get_db)) -> Result:
            return Result(greeting=f"Hello from {db}")

        info = svc.methods["greet"]
        assert "db" in info.dependencies
        assert isinstance(info.dependencies["db"], _Depends)

    def test_bare_decorator(self) -> None:
        """@service.method without parentheses."""
        svc = Service("test")

        @svc.method
        async def simple(payload: Payload) -> Result:
            return Result(greeting="simple")

        assert "simple" in svc.methods

    def test_decorator_with_args(self) -> None:
        """@service.method(generated_name='...')."""
        svc = Service("test")

        @svc.method(generated_name="custom")
        async def original(payload: Payload) -> Result:
            return Result(greeting="custom")

        assert "original" in svc.methods
        assert svc.methods["original"].generated_name == "custom"

    def test_multiple_methods(self) -> None:
        svc = Service("test")

        @svc.method
        async def method_a(payload: Payload) -> Result:
            return Result(greeting="a")

        @svc.method
        async def method_b(payload: Payload) -> Result:
            return Result(greeting="b")

        assert len(svc.methods) == 2
        assert "method_a" in svc.methods
        assert "method_b" in svc.methods
