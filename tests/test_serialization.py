"""Tests for microapi.serialization."""

from __future__ import annotations

import pytest

from microapi.exceptions import SerializationError
from microapi.schema import Schema
from microapi.serialization import deserialize, serialize, to_dict


class UserModel(Schema):
    name: str
    age: int = 0


class TestSerialize:
    def test_serialize_dict(self) -> None:
        data = serialize({"key": "value", "num": 42})
        assert isinstance(data, bytes)
        assert b"key" in data

    def test_serialize_pydantic_model(self) -> None:
        user = UserModel(name="Alice", age=30)
        data = serialize(user)
        assert isinstance(data, bytes)
        assert b"Alice" in data

    def test_serialize_list(self) -> None:
        data = serialize([1, 2, 3])
        assert isinstance(data, bytes)


class TestDeserialize:
    def test_deserialize_bytes(self) -> None:
        result = deserialize(b'{"key": "value"}')
        assert result == {"key": "value"}

    def test_deserialize_string(self) -> None:
        result = deserialize('{"key": "value"}')
        assert result == {"key": "value"}

    def test_deserialize_invalid_raises(self) -> None:
        with pytest.raises(SerializationError):
            deserialize(b"not json")


class TestToDict:
    def test_dict_passthrough(self) -> None:
        d = {"a": 1}
        assert to_dict(d) is d

    def test_pydantic_model(self) -> None:
        user = UserModel(name="Bob", age=25)
        result = to_dict(user)
        assert result == {"name": "Bob", "age": 25}

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(SerializationError):
            to_dict("not a dict")
