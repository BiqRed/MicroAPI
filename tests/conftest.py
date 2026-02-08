"""Shared fixtures for MicroAPI tests."""

from __future__ import annotations

import pytest

from microapi import Schema, Service, types


# ---- Schemas used across tests -------------------------------------------


class UserPayload(Schema):
    user_id: int
    fields: list[str] | None = None


class User(Schema):
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    age: int | None = None


class EchoPayload(Schema):
    message: str


class EchoResult(Schema):
    reply: str


# ---- Service fixtures ----------------------------------------------------


@pytest.fixture
def echo_service() -> Service:
    """A simple echo service for testing."""
    svc = Service("echo")

    @svc.method
    async def echo(payload: EchoPayload) -> EchoResult:
        return EchoResult(reply=f"Echo: {payload.message}")

    return svc


@pytest.fixture
def users_service() -> Service:
    """A users service with all 4 method types."""
    svc = Service("users")

    @svc.method
    async def get_user(payload: UserPayload) -> User:
        return User(username="alice", firstname="Alice", age=30)

    @svc.method
    async def list_users(payload: UserPayload) -> types.Streaming[User]:
        for i in range(3):
            yield User(username=f"user_{i}", age=20 + i)

    @svc.method
    async def add_users(stream: types.Stream[User]) -> EchoResult:
        count = 0
        async for _user in stream:
            count += 1
        return EchoResult(reply=f"Added {count} users")

    @svc.method(generated_name="create_return_user")
    async def bidi_users(stream: types.Stream[User]) -> types.Streaming[User]:
        async for user in stream:
            yield User(username=f"created_{user.username}", age=user.age)

    return svc
