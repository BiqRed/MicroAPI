"""Middleware system for MicroAPI (FastAPI-style request/response chain)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from microapi.protocol import Request, Response

CallNext = Callable[[Request], Awaitable[Response]]


class Middleware(ABC):
    """Base class for MicroAPI middleware.

    Subclass and implement ``__call__`` to intercept requests::

        class AuthMiddleware(Middleware):
            async def __call__(self, request, call_next):
                validate_token(request.metadata.get("authorization"))
                return await call_next(request)
    """

    @abstractmethod
    async def __call__(self, request: Request, call_next: CallNext) -> Response:
        """Process *request* and optionally delegate to *call_next*."""
        ...


class MiddlewareChain:
    """Composes a list of middlewares into a single callable chain."""

    def __init__(self, middlewares: list[Middleware], handler: CallNext) -> None:
        self._handler: CallNext = handler
        # Build the chain from inside out so the first middleware in the
        # list runs first.
        for mw in reversed(middlewares):
            self._handler = self._wrap(mw, self._handler)

    @staticmethod
    def _wrap(mw: Middleware, next_handler: CallNext) -> CallNext:
        """Create a handler that wraps *mw* around *next_handler*."""

        async def _wrapped(request: Request) -> Response:
            return await mw(request, next_handler)

        return _wrapped

    async def __call__(self, request: Request) -> Response:
        return await self._handler(request)
