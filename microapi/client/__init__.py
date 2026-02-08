"""MicroAPI client SDK — base classes for generated client libraries."""

from __future__ import annotations

from microapi.client.base import ClientSchema, Connection
from microapi.client.stream import ClientStream, ClientStreaming

__all__ = [
    "ClientSchema",
    "Connection",
    "ClientStream",
    "ClientStreaming",
]
