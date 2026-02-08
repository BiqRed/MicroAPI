"""MicroAPI exception hierarchy."""

from __future__ import annotations

from typing import Any


class MicroAPIError(Exception):
    """Base exception for all MicroAPI errors."""


class ConfigurationError(MicroAPIError):
    """Raised when framework configuration is invalid."""


class ServiceNotFoundError(MicroAPIError):
    """Raised when a requested service does not exist in the registry."""

    def __init__(self, service: str) -> None:
        self.service = service
        super().__init__(f"Service '{service}' not found")


class MethodNotFoundError(MicroAPIError):
    """Raised when a requested method does not exist in a service."""

    def __init__(self, service: str, method: str) -> None:
        self.service = service
        self.method = method
        super().__init__(f"Method '{method}' not found in service '{service}'")


class SerializationError(MicroAPIError):
    """Raised on serialization / deserialization failure."""


class TransportError(MicroAPIError):
    """Raised on transport-level failures."""


class ConnectionError(TransportError):  # noqa: A001
    """Raised when a transport connection fails."""


class TimeoutError(TransportError):  # noqa: A001
    """Raised when a transport operation times out."""


class DependencyError(MicroAPIError):
    """Raised when dependency resolution fails."""


class MiddlewareError(MicroAPIError):
    """Raised when middleware execution fails."""


class StreamError(MicroAPIError):
    """Raised on stream operation errors."""


class StreamClosedError(StreamError):
    """Raised when operating on a closed stream."""


class ValidationError(MicroAPIError):
    """Raised when payload validation fails."""

    def __init__(self, errors: list[dict[str, Any]] | str) -> None:
        self.errors = errors
        msg = "; ".join(str(e) for e in errors) if isinstance(errors, list) else errors
        super().__init__(f"Validation error: {msg}")
