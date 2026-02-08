"""MicroAPI — a Python microservices framework with FastAPI-like interface."""

from __future__ import annotations

from microapi import types
from microapi.app import MicroAPI
from microapi.dependencies import Depends
from microapi.middleware import Middleware
from microapi.schema import Schema
from microapi.service import Service

__all__ = [
    "MicroAPI",
    "Depends",
    "Middleware",
    "Schema",
    "Service",
    "types",
]
