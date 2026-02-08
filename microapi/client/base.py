"""Client-side base classes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from microapi.protocol import Envelope, MessageType
from microapi.serialization import deserialize, serialize


class ClientSchema(BaseModel):
    """Base schema for client-side generated models."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Connection:
    """Manages the transport-level connection for client calls.

    This is set globally (or per-context) so that generated client
    functions know which transport to use.
    """

    _current: Connection | None = None

    def __init__(self, transport_client: Any) -> None:
        self._transport = transport_client

    @classmethod
    def set_current(cls, connection: Connection) -> None:
        cls._current = connection

    @classmethod
    def get_current(cls) -> Connection:
        if cls._current is None:
            raise RuntimeError(
                "No active MicroAPI connection. "
                "Call Connection.set_current() or use 'async with connection:' first."
            )
        return cls._current

    @property
    def transport(self) -> Any:
        return self._transport

    async def __aenter__(self) -> Connection:
        await self._transport.connect()
        Connection.set_current(self)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._transport.close()
        if Connection._current is self:
            Connection._current = None

    async def request(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a unary RPC request and return the response payload."""
        return await self._transport.request(
            service=service,
            method=method,
            payload=payload,
            metadata=metadata or {},
        )
