"""Hot-reload support using watchfiles."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from microapi._logging import get_logger

logger = get_logger("hot_reload")


def run_with_reload(
    serve_func: Callable[..., Coroutine[Any, Any, None]],
    args: tuple[Any, ...] = (),
    watch_dirs: list[str | Path] | None = None,
) -> None:
    """Run *serve_func* with automatic restart on source changes.

    Uses ``watchfiles`` to monitor Python files in the current directory
    (or specified directories) and restarts the server when changes are
    detected.
    """
    try:
        from watchfiles import run_process
    except ImportError:
        logger.error("watchfiles is required for hot reload. Install with: pip install watchfiles")
        raise

    if watch_dirs is None:
        watch_dirs = [str(Path.cwd())]

    watch_paths = [str(p) for p in watch_dirs]

    logger.info("Hot reload enabled — watching %s", ", ".join(watch_paths))

    def _target() -> None:
        """Target function that runs in the subprocess."""
        asyncio.run(serve_func(*args))

    run_process(
        *watch_paths,
        target=_target,
        watch_filter=_python_filter,
    )


def _python_filter(change: Any, path: str) -> bool:
    """Only trigger reload on Python file changes."""
    return path.endswith(".py")
