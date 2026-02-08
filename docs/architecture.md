# Architecture

This document describes MicroAPI's internal architecture, wire protocol, and design decisions.

## High-Level Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        MicroAPI App                          │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Services  │  │ Middleware │  │  Router   │  │ Lifecycle │ │
│  │ @method   │  │   Chain    │  │ dispatch  │  │  hooks    │ │
│  └──────────┘  └────────────┘  └──────────┘  └───────────┘ │
│                        │                                     │
│                ┌───────┴───────┐                             │
│                │   Protocol    │                             │
│                │ Request/Resp  │                             │
│                └───────┬───────┘                             │
│                        │                                     │
│  ┌─────────────────────┴─────────────────────┐              │
│  │              Transport Layer               │              │
│  │  ┌──────┐ ┌──────┐ ┌────┐ ┌─────┐ ┌────┐ │              │
│  │  │ gRPC │ │ HTTP │ │ WS │ │Kafka│ │AMQP│ │              │
│  │  └──────┘ └──────┘ └────┘ └─────┘ └────┘ │              │
│  └───────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
                         │
                    ┌────┴────┐
                    │ Network │
                    └────┬────┘
                         │
┌──────────────────────────────────────────────────────────────┐
│                     Client Side                              │
│  ┌───────────────┐  ┌────────────┐  ┌──────────────────┐   │
│  │ Generated Lib  │  │ Connection │  │ Transport Client │   │
│  │ users.get_user │──│ set_current│──│ HTTP/gRPC/WS/... │   │
│  └───────────────┘  └────────────┘  └──────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

## Components

### MicroAPI (app.py)

The central application object. Manages:
- Service registration
- Middleware chain
- Lifespan/lifecycle hooks
- Server startup and shutdown
- Code generation (on demand)

### Service (service.py)

A named group of RPC methods. The `@service.method` decorator introspects function signatures to detect:
- Input type (Pydantic `Schema`)
- Output type
- Stream input type (`types.Stream[T]`)
- RPC pattern (unary, server/client/bidi streaming)
- Dependencies (`Depends()`)

### Schema (schema.py)

Alias for a configured Pydantic `BaseModel`:

```python
class Schema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
```

### Router (routing.py)

Dispatches incoming `Request` objects to the correct service method:

1. Look up the service by name
2. Look up the method within the service
3. Apply middleware chain
4. Validate input via Pydantic
5. Resolve dependencies
6. Call the handler
7. Serialize the response

### Middleware (middleware.py)

A chain of middleware functions that wrap request handling:

```
MW1 → MW2 → MW3 → Handler
```

Each middleware receives the request and a `call_next` function. The chain is built once and reused for all requests.

### Dependencies (dependencies.py)

Resolves `Depends()` markers in handler signatures:
- Inspects function parameters
- Detects `Depends` defaults
- Resolves dependencies recursively
- Caches resolved values per-request
- Injects `Request` if type-hinted

### Protocol (protocol.py)

Defines the internal message format:

```python
@dataclass
class Request:
    service: str
    method: str
    payload: dict | list | None
    metadata: dict[str, str]
    id: str  # auto-generated UUID

@dataclass
class Response:
    payload: dict | None
    error: str | None
    status_code: StatusCode
    metadata: dict[str, str]
```

### Envelope (protocol.py)

The wire-level message format used by transports:

```python
@dataclass
class Envelope:
    type: MessageType  # REQUEST, RESPONSE, STREAM_PUSH, STREAM_END
    id: str
    service: str | None
    method: str | None
    payload: dict | list | None
    metadata: dict[str, str]
    error: str | None
    status_code: int
```

Envelopes are serialized to JSON using `orjson` for performance.

### Serialization (serialization.py)

Fast JSON serialization using [orjson](https://github.com/ijl/orjson):

```python
serialize(data) → bytes    # dict/model → JSON bytes
deserialize(data) → dict   # bytes/str → dict
to_dict(obj) → dict        # model/dict → dict
```

## Transport Architecture

Each transport implements two interfaces:

### TransportServer

```python
class TransportServer(ABC):
    @abstractmethod
    async def start(self, router: Router) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
```

### TransportClient

```python
class TransportClient(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def request(
        self, service: str, method: str,
        payload: dict | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict: ...

    async def request_stream(
        self, service: str, method: str,
        payload: dict | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AsyncIterator[dict]: ...
```

### Transport Factory

```python
class Transport(ABC):
    @abstractmethod
    def create_server(self) -> TransportServer: ...

    @abstractmethod
    def create_client(self) -> TransportClient: ...
```

## Wire Protocol

### JSON Envelope

All transports use JSON envelopes for communication:

```json
{
    "type": "request",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "service": "users",
    "method": "get_user",
    "payload": {"user_id": 42},
    "metadata": {"authorization": "Bearer xxx"},
    "error": null,
    "status_code": 0
}
```

### Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| `request` | Client → Server | Initial RPC request |
| `response` | Server → Client | Final response |
| `stream_push` | Server → Client | One item in a stream |
| `stream_end` | Server → Client | End of stream |

### Transport-Specific Encoding

- **HTTP**: JSON body for requests, NDJSON for streaming responses
- **gRPC**: Length-prefixed frames over HTTP/2
- **WebSocket**: JSON text frames with multiplexing via `id`
- **Kafka**: JSON messages on configured topics
- **RabbitMQ**: JSON messages with correlation IDs

## Code Generation Architecture

### Python Generator (generator/python_gen.py)

1. **Collect schemas**: Walk all services and collect unique Pydantic models
2. **Generate types.py**: Convert models to `ClientSchema` subclasses
3. **Generate service modules**: For each method, generate:
   - Unary → async function
   - Server streaming → async generator function
   - Client streaming → `ClientStream` subclass
   - Bidirectional → `ClientStream[T]` subclass with `next()` and `send()`
4. **Generate __init__.py**: Re-export modules and schema types

### Protobuf Generator (generator/protobuf_gen.py)

1. Map Python types to Protobuf types
2. Generate `message` definitions from schemas
3. Generate `service` definitions from methods
4. Handle streaming annotations (`stream` keyword)

## Stream Implementation

### Server-Side Stream (types.py)

`Stream[T]` wraps an `asyncio.Queue`:

```python
class Stream[T]:
    def __init__(self):
        self._queue = asyncio.Queue()
        self._closed = False

    async def _feed(self, item: T) -> None:
        """Used by transport to feed incoming items."""
        self._queue.put_nowait(item)

    async def _close(self) -> None:
        """Signal end of stream."""
        self._queue.put_nowait(_SENTINEL)

    async def __anext__(self) -> T:
        item = await self._queue.get()
        if item is _SENTINEL:
            raise StopAsyncIteration
        return item
```

### Client-Side Stream (client/stream.py)

`ClientStream` buffers messages and sends them on `end()`:

```python
class ClientStream:
    async def _send_raw(self, payload):
        self._buffer.append(payload)

    async def end(self):
        # Send all buffered messages as a list
        return await self._transport.request(
            service=self._service,
            method=self._method,
            payload=self._buffer,
        )
```

## Project Structure

```
microapi/
├── __init__.py            # Public API exports
├── app.py                 # MicroAPI application class
├── service.py             # Service & MethodInfo
├── schema.py              # Schema (Pydantic BaseModel)
├── types.py               # Stream[T], Streaming[T]
├── middleware.py           # Middleware & MiddlewareChain
├── dependencies.py        # Depends() resolver
├── protocol.py            # Request, Response, Envelope, StatusCode
├── serialization.py       # JSON serialization (orjson)
├── routing.py             # Router & request dispatch
├── lifecycle.py           # Lifespan type & default
├── exceptions.py          # Exception hierarchy
├── _logging.py            # Structured logging
├── hot_reload.py          # File watcher
├── transport/
│   ├── __init__.py        # Lazy import helpers
│   ├── base.py            # Abstract Transport/Server/Client
│   ├── grpc/
│   │   ├── __init__.py
│   │   ├── transport.py   # GRPCTransport factory
│   │   ├── server.py      # HTTP/2 server (h2)
│   │   └── client.py      # HTTP/2 client
│   ├── http/
│   │   ├── __init__.py
│   │   ├── transport.py   # HTTPTransport factory
│   │   ├── server.py      # aiohttp server
│   │   └── client.py      # aiohttp client
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── transport.py   # WebSocketTransport factory
│   │   ├── server.py      # websockets server
│   │   └── client.py      # websockets client
│   ├── kafka/
│   │   ├── __init__.py
│   │   └── transport.py   # KafkaTransport (server + client)
│   └── rabbitmq/
│       ├── __init__.py
│       └── transport.py   # RabbitMQTransport (server + client)
├── client/
│   ├── __init__.py
│   ├── base.py            # Connection, ClientSchema
│   └── stream.py          # ClientStream, ClientStreaming
├── generator/
│   ├── __init__.py
│   ├── python_gen.py      # Python client generator
│   └── protobuf_gen.py    # Protobuf generator
├── cli/
│   ├── __init__.py
│   └── main.py            # typer CLI app
└── utils/
    ├── __init__.py
    └── validators.py      # Host/port validators
```

## Design Decisions

### Why Not grpcio?

The standard `grpcio` library:
- Has a complex C extension that can be hard to install
- Doesn't integrate well with asyncio
- Has its own thread pool that conflicts with async frameworks

MicroAPI's custom gRPC implementation uses `h2` (pure Python HTTP/2) and is fully async-native.

### Why JSON Over Protobuf Wire Format?

- JSON is human-readable (easier to debug)
- No `.proto` compilation step required
- Works naturally with Pydantic models
- `orjson` makes JSON serialization very fast
- `.proto` files are still generated for cross-language interop

### Why Buffer Client Streams?

Client streaming sends all buffered messages at once (as a JSON array) rather than true streaming. This simplifies:
- Transport implementations (all use the same `request()` method)
- Code generation (no transport-specific streaming protocols)
- Error handling (single request/response cycle)

For true bidirectional streaming, use the WebSocket transport.

### Why asynccontextmanager Detection?

MicroAPI accepts lifespans as both raw async generators and `@asynccontextmanager`-decorated functions. It uses `inspect.isasyncgenfunction()` to detect the difference and wraps raw generators automatically.
