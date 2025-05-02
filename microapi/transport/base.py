from abc import ABC, abstractmethod
from typing import Callable, Awaitable, AsyncIterator, Protocol

from pydantic import BaseModel


class Stream(Protocol):
    async def send(self, message: str) -> None: ...
    async def recv(self) -> str: ...
    async def close(self) -> None: ...


class Request(BaseModel):
    service: str
    method: str
    payload: str | list[str]
    metadata: dict[str, str]
    stream: Stream | None = None


class Response(BaseModel):
    payload: str | AsyncIterator[str]
    metadata: dict[str, str]
    end_stream: bool = True
    stream: Stream | None = None


Handler = Callable[[Request], Awaitable[Response]]


class Transport(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def serve(self, handler: Handler) -> None:
        raise NotImplementedError
