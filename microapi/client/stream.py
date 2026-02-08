"""Client-side streaming primitives."""

from __future__ import annotations

from typing import Any, AsyncIterator, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ClientStream(Generic[T]):
    """Client-side stream for sending messages to the server.

    Used by generated client code for client-streaming
    and bidirectional-streaming methods.
    """

    def __init__(self, service: str, method: str, transport: Any) -> None:
        self._service = service
        self._method = method
        self._transport = transport
        self._stream: Any = None

    async def _ensure_stream(self) -> Any:
        if self._stream is None:
            self._stream = await self._transport.open_stream(
                self._service, self._method
            )
        return self._stream

    async def send_raw(self, payload: dict[str, Any]) -> None:
        """Send a raw dict payload to the server."""
        stream = await self._ensure_stream()
        await stream.send(payload)

    async def end(self) -> Any:
        """Signal end of client stream and await final response."""
        if self._stream is not None:
            return await self._stream.end()
        return None

    async def next(self) -> T | None:
        """Receive the next server-streamed message (bidi only)."""
        if self._stream is not None:
            data = await self._stream.recv()
            return data
        return None

    async def close(self) -> None:
        """Close the stream."""
        if self._stream is not None:
            await self._stream.close()

    def __aiter__(self) -> AsyncIterator[T]:
        return self._async_iter()

    async def _async_iter(self) -> AsyncIterator[T]:
        """Iterate over server responses (bidi streaming)."""
        if self._stream is not None:
            async for item in self._stream:
                yield item


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
