"""Middleware system for MicroAPI (FastAPI-style request/response chain)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

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
        self._handler = handler
        # Build the chain from inside out so the first middleware in the
        # list runs first.
        for mw in reversed(middlewares):
            next_handler = self._handler

            async def _make_handler(
                request: Request,
                *,
                _mw: Middleware = mw,
                _next: CallNext = next_handler,
            ) -> Response:
                return await _mw(request, _next)

            self._handler = _make_handler

    async def __call__(self, request: Request) -> Response:
        return await self._handler(request)
