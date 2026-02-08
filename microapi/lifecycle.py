"""Application lifecycle management (startup / shutdown hooks)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from microapi.app import MicroAPI

# A Lifespan is any callable that accepts a MicroAPI app and returns
# either a raw async-iterator (async generator) or an async context
# manager.  Both styles are supported automatically.
Lifespan = Callable[["MicroAPI"], Any]


async def default_lifespan(app: MicroAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """Default no-op lifespan (raw async generator)."""
    yield
