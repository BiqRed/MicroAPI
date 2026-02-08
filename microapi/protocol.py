"""Wire protocol message definitions for MicroAPI."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any


class MessageType(StrEnum):
    """Type of a wire-level message."""

    REQUEST = "request"
    RESPONSE = "response"
    STREAM_PUSH = "stream_push"
    STREAM_END = "stream_end"
    ERROR = "error"


class MethodType(StrEnum):
    """RPC method pattern."""

    UNARY = "unary"
    SERVER_STREAMING = "server_streaming"
    CLIENT_STREAMING = "client_streaming"
    BIDI_STREAMING = "bidi_streaming"


class StatusCode(int, Enum):
    """Response status codes (inspired by gRPC status codes)."""

    OK = 0
    CANCELLED = 1
    UNKNOWN = 2
    INVALID_ARGUMENT = 3
    NOT_FOUND = 5
    ALREADY_EXISTS = 6
    PERMISSION_DENIED = 7
    UNAUTHENTICATED = 16
    INTERNAL = 13
    UNAVAILABLE = 14
    UNIMPLEMENTED = 12


# ---------------------------------------------------------------------------
# Request / Response dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Request:
    """Incoming RPC request."""

    service: str
    method: str
    payload: dict[str, Any] | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(slots=True)
class Response:
    """Outgoing RPC response."""

    payload: Any = None
    metadata: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    status_code: StatusCode = StatusCode.OK
    is_streaming: bool = False


@dataclass(slots=True)
class StreamMessage:
    """A single chunk in a streaming exchange."""

    request_id: str
    payload: dict[str, Any] | None = None
    end: bool = False


# ---------------------------------------------------------------------------
# Envelope used by JSON-based transports (HTTP, WS, Kafka, RabbitMQ)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Envelope:
    """Wire-level JSON envelope wrapping every message."""

    type: MessageType
    service: str = ""
    method: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    payload: dict[str, Any] | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    status_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "service": self.service,
            "method": self.method,
            "id": self.id,
            "payload": self.payload,
            "metadata": self.metadata,
            "error": self.error,
            "status_code": self.status_code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Envelope:
        return cls(
            type=MessageType(data["type"]),
            service=data.get("service", ""),
            method=data.get("method", ""),
            id=data.get("id", uuid.uuid4().hex),
            payload=data.get("payload"),
            metadata=data.get("metadata", {}),
            error=data.get("error"),
            status_code=data.get("status_code", 0),
        )
