from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Awaitable, AsyncIterator, Protocol


class Stream(Protocol):
    async def send(self, message: str) -> None: ...
    async def recv(self) -> str: ...
    async def close(self) -> None: ...


@dataclass
class Request:
    service: str
    method: str
    payload: str | list[str]
    metadata: dict[str, str]
    stream: Stream | None = None


@dataclass
class Response:
    payload: str | AsyncIterator[str]
    metadata: dict[str, str]
    end_stream: bool = True
    stream: Stream | None = None


Handler = Callable[[Request], Awaitable[Response]]


class TransportServer(ABC):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def serve(self, handler: Handler) -> None:
        raise NotImplementedError


class TransportClient(ABC):
    pass


class Transport(ABC):
    def get_server(self) -> TransportServer:
        raise NotImplementedError

    def get_client(self) -> TransportClient:
        raise NotImplementedError
