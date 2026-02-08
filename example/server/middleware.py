"""Example middleware for the users service."""

from microapi import Middleware
from microapi.protocol import Request, Response


class AuthMiddleware(Middleware):
    """Simple authentication middleware that logs requests."""

    async def __call__(self, request: Request, call_next) -> Response:
        token = request.metadata.get("authorization", "")
        print(f"[Auth] {request.service}.{request.method} | token={token or 'none'}")
        return await call_next(request)


class LoggingMiddleware(Middleware):
    """Logs every request and response."""

    async def __call__(self, request: Request, call_next) -> Response:
        print(f"[Log] -> {request.service}.{request.method}")
        response = await call_next(request)
        print(f"[Log] <- status={response.status_code.name}")
        return response
