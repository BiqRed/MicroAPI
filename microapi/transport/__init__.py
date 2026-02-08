"""Transport layer — pluggable backends for MicroAPI communication."""

from __future__ import annotations

from microapi.transport.base import Transport, TransportClient, TransportServer

__all__ = [
    "Transport",
    "TransportClient",
    "TransportServer",
]


def __getattr__(name: str):  # noqa: ANN204
    """Lazy-load transport implementations to avoid importing optional deps."""
    _lazy = {
        "GRPCTransport": "microapi.transport.grpc",
        "HTTPTransport": "microapi.transport.http",
        "WebSocketTransport": "microapi.transport.websocket",
        "KafkaTransport": "microapi.transport.kafka",
        "RabbitMQTransport": "microapi.transport.rabbitmq",
    }
    if name in _lazy:
        import importlib

        mod = importlib.import_module(_lazy[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
