"""Client-side streaming primitives."""

from __future__ import annotations

from typing import Any, AsyncIterator, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ClientStream(Generic[T]):
    """Client-side stream for sending messages to the server.

    Used by generated client code for client-streaming and
    bidirectional-streaming methods.

    The stream buffers sent payloads locally; when ``end()`` is called
    the buffered data is sent as a list in a single request via the
    transport's ``request()`` method.
    """

    def __init__(self, service: str, method: str, transport: Any) -> None:
        self._service = service
        self._method = method
        self._transport = transport
        self._buffer: list[dict[str, Any]] = []
        self._response: Any = None

    async def _send_raw(self, payload: dict[str, Any]) -> None:
        """Buffer a payload to be sent when the stream ends."""
        self._buffer.append(payload)

    async def end(self) -> dict[str, Any] | None:
        """Finalize the stream -- send all buffered messages and return response."""
        result = await self._transport.request(
            service=self._service,
            method=self._method,
            payload=self._buffer,
        )
        self._response = result
        return result

    async def next(self) -> T | None:
        """Return the response from ``end()`` (for bidi streaming)."""
        return self._response  # type: ignore[return-value]

    async def close(self) -> None:
        """Close the stream (no-op after end)."""
        self._buffer.clear()


class ClientStreaming(Generic[T]):
    """Client-side async iterator for server-streamed responses.

    Used by generated client code for server-streaming methods.
    """

    def __init__(self, stream: AsyncIterator[dict[str, Any]], model: type[T]) -> None:
        self._stream = stream
        self._model = model

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[T]:
        async for item in self._stream:
            if isinstance(self._model, type) and issubclass(self._model, BaseModel):
                yield self._model.model_validate(item)  # type: ignore[misc]
            else:
                yield item  # type: ignore[misc]
