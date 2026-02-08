"""Connection pool and management utilities."""

from __future__ import annotations

from typing import Any

from microapi.client.base import Connection
from microapi.transport.base import Transport


def create_connection(transport: Transport) -> Connection:
    """Create a :class:`Connection` from a :class:`Transport` factory."""
    client = transport.create_client()
    return Connection(client)
