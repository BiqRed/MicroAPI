"""Serialization utilities for MicroAPI wire protocol."""

from __future__ import annotations

from typing import Any

import orjson
from pydantic import BaseModel

from microapi.exceptions import SerializationError


def serialize(data: Any) -> bytes:
    """Serialize *data* to JSON bytes.

    Pydantic models are serialized via ``model_dump_json()``;
    everything else goes through ``orjson.dumps()``.
    """
    try:
        if isinstance(data, BaseModel):
            return data.model_dump_json().encode("utf-8")
        return orjson.dumps(data)
    except (TypeError, orjson.JSONEncodeError) as exc:
        raise SerializationError(f"Failed to serialize data: {exc}") from exc


def deserialize(data: bytes | str) -> Any:
    """Deserialize JSON *data* into a Python object."""
    try:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return orjson.loads(data)
    except orjson.JSONDecodeError as exc:
        raise SerializationError(f"Failed to deserialize data: {exc}") from exc


def to_dict(data: Any) -> dict[str, Any]:
    """Convert *data* to a plain ``dict``.

    Supports Pydantic models and plain dicts.
    """
    if isinstance(data, BaseModel):
        return data.model_dump(mode="python")
    if isinstance(data, dict):
        return data
    raise SerializationError(f"Cannot convert {type(data).__name__} to dict")
