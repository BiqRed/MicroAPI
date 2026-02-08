# Middleware

MicroAPI uses a middleware chain inspired by FastAPI/Starlette. Each middleware wraps the request/response cycle and can modify requests, responses, or short-circuit the chain.

## Defining Middleware

Subclass `Middleware` and implement the `__call__` method:

```python
from microapi import Middleware
from microapi.protocol import Request, Response

class LoggingMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        print(f"→ {request.service}.{request.method}")
        response = await call_next(request)
        print(f"← {response.status_code.name}")
        return response
```

### Parameters

- **`request`**: The incoming `Request` object with `service`, `method`, `payload`, and `metadata`
- **`call_next`**: An async callable that invokes the next middleware (or the handler)
- **Returns**: A `Response` object

## Registering Middleware

```python
from microapi import MicroAPI

app = MicroAPI()
app.add_middleware(LoggingMiddleware())
app.add_middleware(AuthMiddleware())
```

Or at construction time:

```python
app = MicroAPI(middlewares=[LoggingMiddleware(), AuthMiddleware()])
```

## Execution Order

Middleware executes in **registration order** on the way in, and **reverse order** on the way out:

```python
app.add_middleware(MW1())  # registered first
app.add_middleware(MW2())  # registered second
```

```
Request  →  MW1 (before)  →  MW2 (before)  →  Handler
Response ←  MW1 (after)   ←  MW2 (after)   ←  Handler
```

## Common Patterns

### Authentication

```python
from microapi.protocol import StatusCode

class AuthMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        token = request.metadata.get("authorization")
        if not token:
            return Response(
                error="Missing authorization token",
                status_code=StatusCode.UNAUTHENTICATED,
            )

        user = await verify_token(token)
        if not user:
            return Response(
                error="Invalid token",
                status_code=StatusCode.UNAUTHENTICATED,
            )

        # Attach user info for downstream handlers/dependencies
        request.metadata["user_id"] = str(user.id)
        return await call_next(request)
```

### Logging

```python
import time

class TimingMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        print(
            f"{request.service}.{request.method} "
            f"-> {response.status_code.name} "
            f"({duration:.3f}s)"
        )
        return response
```

### Rate Limiting

```python
from collections import defaultdict
import time

class RateLimitMiddleware(Middleware):
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def __call__(self, request: Request, call_next) -> Response:
        client_id = request.metadata.get("client_id", "anonymous")
        now = time.time()

        # Clean old entries
        self.requests[client_id] = [
            t for t in self.requests[client_id]
            if now - t < self.window
        ]

        if len(self.requests[client_id]) >= self.max_requests:
            return Response(
                error="Rate limit exceeded",
                status_code=StatusCode.RESOURCE_EXHAUSTED,
            )

        self.requests[client_id].append(now)
        return await call_next(request)
```

### Error Handling

```python
class ErrorHandlerMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as e:
            # Log the error, send to Sentry, etc.
            logger.exception("Unhandled error in %s.%s", request.service, request.method)
            return Response(
                error=f"Internal error: {e}",
                status_code=StatusCode.INTERNAL,
            )
```

### Request/Response Transformation

```python
class CompressionMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        # Decompress incoming payload if needed
        if request.metadata.get("content-encoding") == "gzip":
            request.payload = decompress(request.payload)

        response = await call_next(request)

        # Add response metadata
        response.metadata["server-version"] = "1.0"
        return response
```

## Short-Circuiting

Middleware can return a response directly **without** calling `call_next()`. This skips all downstream middleware and the handler:

```python
class MaintenanceMiddleware(Middleware):
    def __init__(self, maintenance_mode: bool = False):
        self.maintenance_mode = maintenance_mode

    async def __call__(self, request: Request, call_next) -> Response:
        if self.maintenance_mode:
            return Response(
                error="Service is under maintenance",
                status_code=StatusCode.UNAVAILABLE,
            )
        return await call_next(request)
```

## Accessing Metadata

The `Request.metadata` dict is the primary way to pass data between middleware layers and to handlers/dependencies:

```python
# In middleware
request.metadata["auth_user"] = "alice"
request.metadata["request_id"] = str(uuid.uuid4())

# In a dependency (accessed via Request injection)
async def get_current_user(req: Request) -> str:
    return req.metadata.get("auth_user", "anonymous")
```

## The Request and Response Objects

### Request

```python
@dataclass
class Request:
    service: str              # Target service name
    method: str               # Target method name
    payload: dict | list | None  # Request data
    metadata: dict[str, str]  # Headers/metadata (mutable)
    id: str                   # Unique request ID (auto-generated)
```

### Response

```python
@dataclass
class Response:
    payload: dict | None = None        # Response data
    error: str | None = None           # Error message (if any)
    status_code: StatusCode = StatusCode.OK
    metadata: dict[str, str] = {}      # Response metadata
```

### StatusCode

Available status codes (modeled after gRPC):

```python
class StatusCode(IntEnum):
    OK = 0
    CANCELLED = 1
    UNKNOWN = 2
    INVALID_ARGUMENT = 3
    NOT_FOUND = 5
    ALREADY_EXISTS = 6
    PERMISSION_DENIED = 7
    RESOURCE_EXHAUSTED = 8
    UNAUTHENTICATED = 16
    UNAVAILABLE = 14
    INTERNAL = 13
```
