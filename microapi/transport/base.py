"""Abstract transport interfaces for MicroAPI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from microapi.routing import Router


class TransportServer(ABC):
    """Base class for server-side transport implementations."""

    @abstractmethod
    async def start(self, router: Router) -> None:
        """Start accepting connections and dispatching to *router*."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the transport server."""
        ...

    @abstractmethod
    async def serve_forever(self) -> None:
        """Block until the server is stopped."""
        ...


class TransportClient(ABC):
    """Base class for client-side transport implementations."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish a connection to the remote server."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        ...

    @abstractmethod
    async def request(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a unary request and return the response payload."""
        ...


class Transport(ABC):
    """Factory that creates server and client transport instances."""

    @abstractmethod
    def create_server(self) -> TransportServer:
        """Create a server-side transport."""
        ...

    @abstractmethod
    def create_client(self) -> TransportClient:
        """Create a client-side transport."""
        ...
