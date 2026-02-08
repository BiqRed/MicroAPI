"""Core type definitions for MicroAPI streaming and service methods."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Generic, TypeVar

from microapi.exceptions import StreamClosedError

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Streaming: type alias for server-side streaming responses (async generator)
# ---------------------------------------------------------------------------
Streaming = AsyncGenerator[T, None]

# ---------------------------------------------------------------------------
# Stream: incoming stream of typed messages from a client
# ---------------------------------------------------------------------------
_SENTINEL = object()


class Stream(Generic[T]):
    """An incoming stream of typed messages from a client.

    Used as a parameter type annotation in service methods to receive
    client-streaming or bidirectional-streaming data.

    Example::

        @service.method
        async def add_users(stream: Stream[User]) -> None:
            async for user in stream:
                await db.create(user)
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._closed: bool = False

    # -- async iterator protocol ------------------------------------------

    def __aiter__(self) -> Stream[T]:
        return self

    async def __anext__(self) -> T:
        item = await self._queue.get()
        if item is _SENTINEL:
            raise StopAsyncIteration
        return item  # type: ignore[return-value]

    # -- internal API (called by transport / router) -----------------------

    async def _feed(self, item: T) -> None:
        """Push an item into the stream."""
        if self._closed:
            raise StreamClosedError("Cannot feed into a closed stream")
        await self._queue.put(item)

    async def _close(self) -> None:
        """Signal that no more items will arrive."""
        if not self._closed:
            self._closed = True
            await self._queue.put(_SENTINEL)

    @property
    def closed(self) -> bool:
        """Whether the stream has been closed."""
        return self._closed
