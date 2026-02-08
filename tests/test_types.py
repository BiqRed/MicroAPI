"""Tests for microapi.types (Stream, Streaming)."""

from __future__ import annotations

import asyncio

import pytest

from microapi.exceptions import StreamClosedError
from microapi.types import Stream


class TestStream:
    @pytest.mark.asyncio
    async def test_feed_and_iterate(self) -> None:
        stream: Stream[int] = Stream()
        await stream._feed(1)
        await stream._feed(2)
        await stream._feed(3)
        await stream._close()

        items = []
        async for item in stream:
            items.append(item)

        assert items == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_empty_stream(self) -> None:
        stream: Stream[int] = Stream()
        await stream._close()

        items = []
        async for item in stream:
            items.append(item)

        assert items == []

    @pytest.mark.asyncio
    async def test_closed_property(self) -> None:
        stream: Stream[int] = Stream()
        assert not stream.closed
        await stream._close()
        assert stream.closed

    @pytest.mark.asyncio
    async def test_feed_after_close_raises(self) -> None:
        stream: Stream[int] = Stream()
        await stream._close()

        with pytest.raises(StreamClosedError):
            await stream._feed(1)

    @pytest.mark.asyncio
    async def test_concurrent_feed_and_iterate(self) -> None:
        stream: Stream[int] = Stream()
        received: list[int] = []

        async def producer() -> None:
            for i in range(5):
                await stream._feed(i)
                await asyncio.sleep(0.01)
            await stream._close()

        async def consumer() -> None:
            async for item in stream:
                received.append(item)

        await asyncio.gather(producer(), consumer())
        assert received == [0, 1, 2, 3, 4]
