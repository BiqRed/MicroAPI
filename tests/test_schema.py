"""Tests for microapi.schema."""

from __future__ import annotations

from microapi.schema import Schema


class UserSchema(Schema):
    name: str
    age: int = 0
    email: str | None = None


class TestSchema:
    def test_basic_creation(self) -> None:
        user = UserSchema(name="Alice", age=30)
        assert user.name == "Alice"
        assert user.age == 30
        assert user.email is None

    def test_from_dict(self) -> None:
        user = UserSchema.model_validate({"name": "Bob", "age": 25})
        assert user.name == "Bob"
        assert user.age == 25

    def test_to_dict(self) -> None:
        user = UserSchema(name="Charlie")
        data = user.model_dump()
        assert data == {"name": "Charlie", "age": 0, "email": None}

    def test_from_attributes(self) -> None:
        class Obj:
            name = "Dave"
            age = 40
            email = "dave@test.com"

        user = UserSchema.model_validate(Obj(), from_attributes=True)
        assert user.name == "Dave"

    def test_json_serialization(self) -> None:
        user = UserSchema(name="Eve", age=28)
        json_str = user.model_dump_json()
        assert '"name":"Eve"' in json_str or '"name": "Eve"' in json_str

    def test_optional_fields(self) -> None:
        user = UserSchema(name="Frank")
        assert user.age == 0
        assert user.email is None
