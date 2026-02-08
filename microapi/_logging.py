"""MicroAPI logging configuration."""

from __future__ import annotations

import logging
import sys

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = "microapi") -> logging.Logger:
    """Get a named logger under the ``microapi`` namespace."""
    if name and not name.startswith("microapi"):
        name = f"microapi.{name}"
    return logging.getLogger(name)


def configure_logging(
    level: int | str = logging.INFO,
    fmt: str = _DEFAULT_FORMAT,
    datefmt: str = _DEFAULT_DATE_FORMAT,
) -> None:
    """Configure the root ``microapi`` logger with a stream handler."""
    root = logging.getLogger("microapi")
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        root.addHandler(handler)
    root.setLevel(level)


logger = get_logger()
