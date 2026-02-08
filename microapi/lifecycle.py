"""Application lifecycle management (startup / shutdown hooks)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable

if TYPE_CHECKING:
    from microapi.app import MicroAPI

Lifespan = Callable[["MicroAPI"], AsyncIterator[None]]


@asynccontextmanager
async def default_lifespan(app: MicroAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """Default no-op lifespan context manager."""
    yield
