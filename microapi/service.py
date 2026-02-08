"""Service registration and method decorator."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin, get_type_hints

from microapi._logging import logger
from microapi.dependencies import _Depends
from microapi.protocol import MethodType
from microapi.schema import Schema
from microapi.types import Stream


@dataclass(slots=True)
class MethodInfo:
    """Metadata about a registered service method."""

    func: Callable[..., Any]
    name: str
    generated_name: str
    input_type: type[Schema] | None
    output_type: type | None
    method_type: MethodType
    dependencies: dict[str, _Depends] = field(default_factory=dict)
    stream_input_type: type | None = None


class Service:
    """A named group of RPC methods.

    Example::

        service = Service("users")

        @service.method
        async def get_user(payload: GetUserPayload) -> User:
            ...

        @service.method(generated_name="create_return_user")
        async def add_and_get_users(stream: Stream[User]) -> Streaming[User]:
            async for user in stream:
                yield ...
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.methods: dict[str, MethodInfo] = {}

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    def method(
        self,
        func: Callable[..., Any] | None = None,
        *,
        generated_name: str | None = None,
    ) -> Any:
        """Register a function as an RPC method on this service.

        Supports bare ``@service.method`` and
        ``@service.method(generated_name="...")`` forms.
        """
        if func is not None:
            # Called as @service.method (no parentheses)
            return self._register(func, generated_name=generated_name)

        # Called as @service.method(...) with keyword args
        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            return self._register(f, generated_name=generated_name)

        return decorator

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _register(
        self,
        func: Callable[..., Any],
        *,
        generated_name: str | None = None,
    ) -> Callable[..., Any]:
        hints = get_type_hints(func)
        sig = inspect.signature(func)

        input_type: type[Schema] | None = None
        output_type: type | None = None
        stream_input_type: type | None = None
        has_client_stream = False
        has_server_stream = False
        dependencies: dict[str, _Depends] = {}

        # Inspect parameters
        for param in sig.parameters.values():
            ann = hints.get(param.name)
            default = param.default

            # Collect dependencies (Depends(...) defaults)
            if isinstance(default, _Depends):
                dependencies[param.name] = default
                continue

            if ann is None:
                continue

            origin = get_origin(ann)

            # Client stream parameter: Stream[T]
            if origin is Stream or ann is Stream:
                has_client_stream = True
                args = get_args(ann)
                if args:
                    stream_input_type = args[0]
                continue

            # Payload parameter: a Schema subclass
            if input_type is None:
                try:
                    if isinstance(ann, type) and issubclass(ann, Schema):
                        input_type = ann
                except TypeError:
                    pass

        # Inspect return type
        return_ann = hints.get("return")
        if return_ann is not None:
            origin = get_origin(return_ann)
            import types as _bt
            from collections.abc import AsyncGenerator as AbcAsyncGenerator
            from collections.abc import AsyncGenerator as TypingAsyncGenerator

            if origin in (TypingAsyncGenerator, AbcAsyncGenerator, _bt.AsyncGeneratorType):
                has_server_stream = True
                args = get_args(return_ann)
                if args:
                    output_type = args[0]
            elif return_ann is not type(None):
                output_type = return_ann

        # Async-generator functions are always server-streaming
        if inspect.isasyncgenfunction(func):
            has_server_stream = True

        # Determine method type
        if has_client_stream and has_server_stream:
            method_type = MethodType.BIDI_STREAMING
        elif has_client_stream:
            method_type = MethodType.CLIENT_STREAMING
        elif has_server_stream:
            method_type = MethodType.SERVER_STREAMING
        else:
            method_type = MethodType.UNARY

        name = func.__name__
        info = MethodInfo(
            func=func,
            name=name,
            generated_name=generated_name or name,
            input_type=input_type,
            output_type=output_type,
            method_type=method_type,
            dependencies=dependencies,
            stream_input_type=stream_input_type,
        )
        self.methods[name] = info
        logger.debug("Registered %s.%s (%s)", self.name, name, method_type.value)
        return func
