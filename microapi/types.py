from typing import AsyncGenerator, AsyncIterator, Generic, TypeVar, Awaitable

T = TypeVar("T")


class Stream(Generic[T]):
    def __init__(self, iterator: AsyncIterator[T]):
        self._iterator = iterator

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iterator


Streaming = AsyncGenerator[T, None]


class Lifespan:
    pass
