"""Tests for microapi.dependencies."""

from __future__ import annotations

import pytest

from microapi import Depends, Schema, Service
from microapi.dependencies import DependencyResolver, _Depends
from microapi.protocol import Request
from microapi.routing import Router


class Payload(Schema):
    name: str


class Result(Schema):
    greeting: str


class TestDependsFunction:
    def test_depends_returns_marker(self) -> None:
        def get_db():
            return "db"

        dep = Depends(get_db)
        assert isinstance(dep, _Depends)
        assert dep.dependency is get_db
        assert dep.use_cache is True

    def test_depends_no_cache(self) -> None:
        def get_db():
            return "db"

        dep = Depends(get_db, use_cache=False)
        assert dep.use_cache is False


class TestDependencyResolver:
    @pytest.mark.asyncio
    async def test_resolve_sync_dependency(self) -> None:
        def get_value():
            return 42

        resolver = DependencyResolver()
        deps = {"val": _Depends(get_value)}
        result = await resolver.resolve(deps, Request(service="s", method="m"))
        assert result == {"val": 42}

    @pytest.mark.asyncio
    async def test_resolve_async_dependency(self) -> None:
        async def get_value():
            return "async_val"

        resolver = DependencyResolver()
        deps = {"val": _Depends(get_value)}
        result = await resolver.resolve(deps, Request(service="s", method="m"))
        assert result == {"val": "async_val"}

    @pytest.mark.asyncio
    async def test_caching(self) -> None:
        call_count = 0

        def get_value():
            nonlocal call_count
            call_count += 1
            return call_count

        resolver = DependencyResolver()
        dep = _Depends(get_value, use_cache=True)
        deps = {"a": dep, "b": dep}
        result = await resolver.resolve(deps, Request(service="s", method="m"))

        # Both should get the same cached value
        assert result["a"] == result["b"] == 1
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_caching(self) -> None:
        call_count = 0

        def get_value():
            nonlocal call_count
            call_count += 1
            return call_count

        resolver = DependencyResolver()
        dep_a = _Depends(get_value, use_cache=False)
        dep_b = _Depends(get_value, use_cache=False)
        deps = {"a": dep_a, "b": dep_b}
        result = await resolver.resolve(deps, Request(service="s", method="m"))

        assert result["a"] == 1
        assert result["b"] == 2

    @pytest.mark.asyncio
    async def test_dependency_in_service_method(self) -> None:
        async def get_prefix():
            return "Hi"

        svc = Service("dep_test")

        @svc.method
        async def greet(payload: Payload, prefix: str = Depends(get_prefix)) -> Result:
            return Result(greeting=f"{prefix}, {payload.name}!")

        router = Router()
        router.register_service(svc)

        req = Request(service="dep_test", method="greet", payload={"name": "World"})
        resp = await router.handle_request(req)

        assert resp.payload["greeting"] == "Hi, World!"
