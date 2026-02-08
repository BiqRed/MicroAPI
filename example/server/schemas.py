"""Pydantic schemas for the users service."""

from microapi import Schema


class User(Schema):
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    age: int | None = None


class GetUserPayload(Schema):
    user_id: int
    fields: list[str] | None = None


class GetUsersPayload(Schema):
    fields: list[str] | None = None
