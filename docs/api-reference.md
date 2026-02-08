# API Reference

Complete reference for all public classes, functions, and types in MicroAPI.

---

## `microapi` — Main Package

### `MicroAPI`

```python
class MicroAPI:
    def __init__(
        self,
        *,
        services: Sequence[Service] | None = None,
        middlewares: Sequence[Middleware] | None = None,
        on_startup: Sequence[Callable[[], Any]] | None = None,
        on_shutdown: Sequence[Callable[[], Any]] | None = None,
        lifespan: Lifespan | None = None,
        version: int = 1,
    ) -> None: ...
```

The main application class.

**Parameters:**
- `services` — Services to register on creation
- `middlewares` — Middleware to add on creation
- `on_startup` — Startup hook functions
- `on_shutdown` — Shutdown hook functions
- `lifespan` — Lifespan context manager (raw async gen or `@asynccontextmanager` decorated)
- `version` — API version number

**Methods:**

| Method | Description |
|--------|-------------|
| `add_service(service)` | Register a `Service` |
| `add_middleware(middleware)` | Add a `Middleware` |
| `on_startup(func)` | Decorator to register a startup hook |
| `on_shutdown(func)` | Decorator to register a shutdown hook |
| `run(transport, **kwargs)` | Start the server (blocking) |

**`run()` parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `transport` | `Transport` | required | Transport backend |
| `auto_generate_lib` | `bool` | `False` | Generate client lib on startup |
| `generated_lib_dir` | `str \| Path` | `"lib"` | Output dir for generated lib |
| `generate_protos` | `bool` | `False` | Generate .proto files |
| `protos_dir` | `str \| Path` | `"protos"` | Output dir for .proto files |
| `reload` | `bool` | `False` | Enable hot reload |
| `log_level` | `str` | `"INFO"` | Logging level |

---

### `Service`

```python
class Service:
    def __init__(self, name: str) -> None: ...
```

A named group of RPC methods.

**Properties:**
- `name: str` — Service name
- `methods: dict[str, MethodInfo]` — Registered methods

**Decorator:**

```python
@service.method
async def my_method(payload: MyPayload) -> MyResult: ...

@service.method(generated_name="custom_name")
async def my_method(payload: MyPayload) -> MyResult: ...
```

---

### `Schema`

```python
class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
```

Base class for all data schemas. Extends Pydantic's `BaseModel`.

---

### `Middleware`

```python
class Middleware(ABC):
    @abstractmethod
    async def __call__(self, request: Request, call_next: CallNext) -> Response: ...
```

Base class for middleware. Override `__call__` to implement.

---

### `Depends`

```python
class Depends:
    def __init__(self, dependency: Callable, *, use_cache: bool = True) -> None: ...
```

Marker for dependency injection.

**Parameters:**
- `dependency` — Callable to resolve (sync or async)
- `use_cache` — Whether to cache the result per-request (default: `True`)

---

## `microapi.types` — Type Helpers

### `Stream[T]`

```python
class Stream[T]:
    closed: bool

    async def __aiter__(self) -> AsyncIterator[T]: ...
    async def __anext__(self) -> T: ...
```

Incoming message stream for client/bidi streaming methods. Use with `async for`.

### `Streaming[T]`

```python
Streaming = AsyncIterator
```

Type alias for return annotation of server/bidi streaming methods. Use `yield` in your handler.

---

## `microapi.protocol` — Wire Protocol

### `Request`

```python
@dataclass
class Request:
    service: str
    method: str
    payload: dict[str, Any] | list[Any] | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)
```

### `Response`

```python
@dataclass
class Response:
    payload: dict[str, Any] | None = None
    error: str | None = None
    status_code: StatusCode = StatusCode.OK
    metadata: dict[str, str] = field(default_factory=dict)
```

### `StatusCode`

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
    INTERNAL = 13
    UNAVAILABLE = 14
    UNAUTHENTICATED = 16
```

### `MessageType`

```python
class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    STREAM_PUSH = "stream_push"
    STREAM_END = "stream_end"
```

### `MethodType`

```python
class MethodType(str, Enum):
    UNARY = "unary"
    SERVER_STREAMING = "server_streaming"
    CLIENT_STREAMING = "client_streaming"
    BIDI_STREAMING = "bidi_streaming"
```

### `Envelope`

```python
@dataclass
class Envelope:
    type: MessageType
    id: str
    service: str | None
    method: str | None
    payload: dict | list | None
    metadata: dict[str, str]
    error: str | None
    status_code: int

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> Envelope: ...
```

---

## `microapi.exceptions` — Exceptions

| Exception | Status Code | Description |
|-----------|-------------|-------------|
| `MicroAPIError` | — | Base exception |
| `NotFoundError` | `NOT_FOUND` | Resource not found |
| `ValidationError` | `INVALID_ARGUMENT` | Validation failed |
| `TransportError` | varies | Transport-level error |
| `StreamClosedError` | — | Writing to a closed stream |

---

## `microapi.client.base` — Client SDK

### `Connection`

```python
class Connection:
    def __init__(self, transport_client: TransportClient) -> None: ...

    @classmethod
    def set_current(cls, connection: Connection) -> None: ...

    @classmethod
    def get_current(cls) -> Connection: ...

    async def request(
        self,
        service: str,
        method: str,
        payload: dict | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict: ...

    async def request_stream(
        self,
        service: str,
        method: str,
        payload: dict | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AsyncIterator[dict]: ...

    async def __aenter__(self) -> Connection: ...
    async def __aexit__(self, *exc) -> None: ...
```

Use as async context manager to manage the connection lifecycle.

### `ClientSchema`

```python
class ClientSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
```

Base class for generated client-side schemas.

---

## `microapi.client.stream` — Client Streaming

### `ClientStream[T]`

```python
class ClientStream[T]:
    def __init__(self, service: str, method: str, transport: Any) -> None: ...

    async def _send_raw(self, payload: dict) -> None: ...
    async def end(self) -> dict | None: ...
    async def next(self) -> Any: ...
    async def close(self) -> None: ...
```

Base class for generated client-side stream classes.

### `ClientStreaming[T]`

```python
class ClientStreaming[T]:
    def __init__(self, stream: AsyncIterator[dict], model: type[T]) -> None: ...

    def __aiter__(self) -> AsyncIterator[T]: ...
```

Client-side async iterator for server-streamed responses.

---

## `microapi.transport` — Transport Layer

### `Transport` (Abstract)

```python
class Transport(ABC):
    def create_server(self) -> TransportServer: ...
    def create_client(self) -> TransportClient: ...
```

### `TransportServer` (Abstract)

```python
class TransportServer(ABC):
    async def start(self, router: Router) -> None: ...
    async def stop(self) -> None: ...
```

### `TransportClient` (Abstract)

```python
class TransportClient(ABC):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def request(self, service, method, payload, metadata) -> dict: ...
    async def request_stream(self, service, method, payload, metadata) -> AsyncIterator[dict]: ...
```

### Concrete Transports

| Class | Module | Install |
|-------|--------|---------|
| `HTTPTransport(host, port)` | `microapi.transport.http` | `microapi[http]` |
| `GRPCTransport(host, port, ssl_context)` | `microapi.transport.grpc` | `microapi[grpc]` |
| `WebSocketTransport(host, port)` | `microapi.transport.websocket` | `microapi[ws]` |
| `KafkaTransport(bootstrap_servers, ...)` | `microapi.transport.kafka` | `microapi[kafka]` |
| `RabbitMQTransport(url, ...)` | `microapi.transport.rabbitmq` | `microapi[rabbitmq]` |

---

## `microapi.generator` — Code Generation

### `generate_python_lib`

```python
def generate_python_lib(services: dict[str, Service], output_dir: Path) -> None: ...
```

Generate a fully-typed Python client library from service definitions.

### `generate_proto_files`

```python
def generate_proto_files(services: dict[str, Service], output_dir: Path) -> None: ...
```

Generate `.proto` files from service definitions.

---

## `microapi.service` — Service Internals

### `MethodInfo`

```python
@dataclass
class MethodInfo:
    name: str                              # Method name
    handler: Callable                      # The async function
    input_type: type[BaseModel] | None     # Pydantic input schema
    output_type: type | None               # Return type
    stream_input_type: type | None         # Stream item type
    method_type: MethodType                # UNARY, SERVER_STREAMING, etc.
    generated_name: str                    # Name for code generation
    dependencies: dict[str, Depends]       # Depends() parameters
```
