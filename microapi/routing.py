"""Request routing and dispatch."""

from __future__ import annotations

import inspect
from typing import Any, AsyncIterator, get_origin, get_type_hints

from microapi._logging import logger
from microapi.dependencies import DependencyResolver
from microapi.exceptions import (
    MethodNotFoundError,
    ServiceNotFoundError,
    ValidationError,
)
from microapi.middleware import CallNext, Middleware, MiddlewareChain
from microapi.protocol import MethodType, Request, Response, StatusCode
from microapi.serialization import to_dict
from microapi.service import MethodInfo, Service
from microapi.types import Stream


class Router:
    """Central dispatcher that routes requests to service methods."""

    def __init__(self) -> None:
        self._services: dict[str, Service] = {}
        self._middlewares: list[Middleware] = []
        self._dep_resolver = DependencyResolver()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_service(self, service: Service) -> None:
        if service.name in self._services:
            raise ValueError(f"Service '{service.name}' is already registered")
        self._services[service.name] = service
        logger.info("Registered service '%s' with %d method(s)", service.name, len(service.methods))

    def add_middleware(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    @property
    def services(self) -> dict[str, Service]:
        return self._services

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_method_info(self, service: str, method: str) -> MethodInfo:
        svc = self._services.get(service)
        if svc is None:
            raise ServiceNotFoundError(service)
        meth = svc.methods.get(method)
        if meth is None:
            raise MethodNotFoundError(service, method)
        return meth

    def get_method_type(self, service: str, method: str) -> MethodType:
        return self.get_method_info(service, method).method_type

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def handle_request(
        self,
        request: Request,
        client_stream: Stream[Any] | None = None,
    ) -> Response:
        """Route *request* through middleware and dispatch to the service method."""
        try:
            method_info = self.get_method_info(request.service, request.method)
        except (ServiceNotFoundError, MethodNotFoundError) as exc:
            return Response(
                error=str(exc),
                status_code=StatusCode.NOT_FOUND,
            )

        async def _inner_handler(req: Request) -> Response:
            return await self._dispatch(req, method_info, client_stream)

        chain = MiddlewareChain(self._middlewares, _inner_handler)

        try:
            return await chain(request)
        except Exception as exc:
            logger.exception("Unhandled error in %s.%s", request.service, request.method)
            return Response(
                error=str(exc),
                status_code=StatusCode.INTERNAL,
            )

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        request: Request,
        method_info: MethodInfo,
        client_stream: Stream[Any] | None = None,
    ) -> Response:
        # Resolve dependencies
        resolved_deps = await self._dep_resolver.resolve(method_info.dependencies, request)

        # Build kwargs
        kwargs: dict[str, Any] = {}
        kwargs.update(resolved_deps)

        sig = inspect.signature(method_info.func)
        hints = get_type_hints(method_info.func)

        if method_info.method_type in (MethodType.CLIENT_STREAMING, MethodType.BIDI_STREAMING):
            # Inject client stream
            for param_name in sig.parameters:
                ann = hints.get(param_name)
                if ann is not None and (get_origin(ann) is Stream or ann is Stream):
                    kwargs[param_name] = client_stream
                    break
        else:
            # Deserialize payload into input schema
            if method_info.input_type is not None and request.payload:
                try:
                    payload_obj = method_info.input_type.model_validate(request.payload)
                except Exception as exc:
                    return Response(
                        error=str(exc),
                        status_code=StatusCode.INVALID_ARGUMENT,
                    )
                # Find the payload parameter name
                for param_name in sig.parameters:
                    if param_name not in resolved_deps:
                        ann = hints.get(param_name)
                        if ann is not None and isinstance(ann, type) and issubclass(ann, method_info.input_type):
                            kwargs[param_name] = payload_obj
                            break

        # Call the method
        result = method_info.func(**kwargs)

        if method_info.method_type in (MethodType.SERVER_STREAMING, MethodType.BIDI_STREAMING):
            # Return the async generator wrapped in a streaming Response.
            # The transport is responsible for iterating it.
            return Response(payload=result, is_streaming=True)

        # Unary / client-streaming: await the result
        if inspect.isawaitable(result):
            result = await result

        if result is None:
            return Response(payload=None, status_code=StatusCode.OK)

        try:
            payload = to_dict(result)
        except Exception:
            payload = result

        return Response(payload=payload, status_code=StatusCode.OK)
