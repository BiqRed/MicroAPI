"""Client-side base classes."""

from __future__ import annotations

from typing import Any, AsyncIterator

from pydantic import BaseModel, ConfigDict


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

    async def request_stream(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a request and iterate over a streaming response.

        Falls back to wrapping a unary response in a single-item
        iterator if the transport lacks native streaming.
        """
        if hasattr(self._transport, "request_stream"):
            async for item in self._transport.request_stream(
                service=service,
                method=method,
                payload=payload,
                metadata=metadata or {},
            ):
                yield item
        else:
            # Fallback: unary request, yield result(s)
            result = await self._transport.request(
                service=service,
                method=method,
                payload=payload,
                metadata=metadata or {},
            )
            if isinstance(result, list):
                for item in result:
                    yield item
            else:
                yield result
