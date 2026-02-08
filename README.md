# MicroAPI

A Python microservices framework that lets your services communicate as if calling regular Python functions. Built with a **FastAPI-like** interface, full **Pydantic** typing, and multiple transport backends.

## Features

- **FastAPI-like Interface** — Decorate async functions to expose them as RPC methods with `@service.method`
- **Full Type Safety** — Pydantic schemas for validation + generated client code with complete type hints
- **5 Transport Backends** — gRPC (custom h2), HTTP, WebSocket, Kafka, RabbitMQ
- **4 RPC Patterns** — Unary, server streaming, client streaming, bidirectional streaming
- **Auto Code Generation** — Generate typed Python client libraries and `.proto` files automatically
- **Middleware & Dependencies** — FastAPI-style middleware chain and `Depends()` injection
- **CLI Tool** — `microapi run`, `microapi generate`, `microapi init`, `microapi info`
- **Hot Reload** — Auto-restart on file changes during development

## Installation

```bash
# Core
pip install microapi

# With specific transport
pip install microapi[grpc]      # gRPC (h2-based)
pip install microapi[http]      # HTTP (aiohttp)
pip install microapi[ws]        # WebSocket
pip install microapi[kafka]     # Apache Kafka
pip install microapi[rabbitmq]  # RabbitMQ

# Everything
pip install microapi[all]
```

## Quick Start

### 1. Define Your Service

```python
# server/schemas.py
from microapi import Schema

class User(Schema):
    username: str | None = None
    firstname: str | None = None
    age: int | None = None

class GetUserPayload(Schema):
    user_id: int
    fields: list[str] | None = None
```

```python
# server/service.py
from microapi import Service, types
from schemas import GetUserPayload, User

service = Service("users")

@service.method
async def get_user(payload: GetUserPayload) -> User:
    # Fetch from your database
    return User(username="alice", firstname="Alice", age=30)

@service.method
async def list_users(payload: GetUserPayload) -> types.Streaming[User]:
    users = await db.get_all_users()
    for user in users:
        yield User.model_validate(user)
```

### 2. Run the Server

```python
# server/main.py
from microapi import MicroAPI
from microapi.transport.http import HTTPTransport
from service import service

app = MicroAPI()
app.add_service(service)

if __name__ == "__main__":
    app.run(
        transport=HTTPTransport(host="0.0.0.0", port=8080),
        auto_generate_lib=True,
        generated_lib_dir="lib",
    )
```

Or via CLI:

```bash
microapi run server.main:app --transport http --port 8080 --generate-lib
```

### 3. Use the Generated Client

The `auto_generate_lib=True` flag creates a fully-typed Python library:

```python
# client.py
import asyncio
from lib import users
from microapi.client.base import Connection
from microapi.transport.http import HTTPTransport

async def main():
    transport = HTTPTransport(host="127.0.0.1", port=8080)
    conn = Connection(transport.create_client())

    async with conn:
        # Call it like a regular function — fully typed!
        user = await users.get_user(user_id=1)
        print(user.username)  # IDE autocomplete works!

asyncio.run(main())
```

## RPC Method Patterns

MicroAPI supports all four RPC patterns, detected automatically from type hints:

### Unary (Request → Response)

```python
@service.method
async def get_user(payload: GetUserPayload) -> User:
    return User(username="alice")
```

### Server Streaming (Request → Stream of Responses)

```python
@service.method
async def list_users(payload: ListPayload) -> types.Streaming[User]:
    for user in await get_all():
        yield user
```

### Client Streaming (Stream of Requests → Response)

```python
@service.method
async def add_users(stream: types.Stream[User]) -> None:
    async for user in stream:
        await save(user)
```

### Bidirectional Streaming (Stream ↔ Stream)

```python
@service.method(generated_name="create_return_user")
async def process_users(stream: types.Stream[User]) -> types.Streaming[User]:
    async for user in stream:
        created = await create(user)
        yield created
```

## Transports

### gRPC (Custom HTTP/2)

Built from scratch using `h2` — no `grpcio` dependency. Supports standard gRPC wire format with JSON payloads.

```python
from microapi.transport.grpc import GRPCTransport

app.run(transport=GRPCTransport(host="0.0.0.0", port=50051))
```

Features:
- HTTP/2 with flow control
- `.proto` file generation for cross-language interop
- SSL/TLS support

### HTTP

Standard HTTP/1.1 transport using `aiohttp`. Methods map to `POST /{service}/{method}`.

```python
from microapi.transport.http import HTTPTransport

app.run(transport=HTTPTransport(host="0.0.0.0", port=8080))
```

Features:
- JSON request/response
- NDJSON for server streaming
- Health check at `GET /health`

### WebSocket

Persistent connection with multiplexed request/response messages.

```python
from microapi.transport.websocket import WebSocketTransport

app.run(transport=WebSocketTransport(host="0.0.0.0", port=8765))
```

Features:
- Single connection, multiple concurrent requests
- Full streaming support
- Low latency

### Kafka

Event-driven transport using Apache Kafka as the message broker.

```python
from microapi.transport.kafka import KafkaTransport

app.run(transport=KafkaTransport(
    bootstrap_servers="kafka:9092",
    request_topic="my-requests",
    response_topic="my-responses",
))
```

### RabbitMQ

Queue-based transport using RabbitMQ.

```python
from microapi.transport.rabbitmq import RabbitMQTransport

app.run(transport=RabbitMQTransport(
    url="amqp://guest:guest@rabbitmq:5672/",
    request_queue="my-requests",
))
```

## Middleware

Middleware follows the FastAPI pattern — a chain of functions that wrap the request/response cycle:

```python
from microapi import Middleware
from microapi.protocol import Request, Response

class AuthMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        token = request.metadata.get("authorization")
        if not token:
            return Response(error="Unauthorized", status_code=StatusCode.UNAUTHENTICATED)
        return await call_next(request)

class LoggingMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        print(f"→ {request.service}.{request.method}")
        response = await call_next(request)
        print(f"← {response.status_code.name}")
        return response

app = MicroAPI()
app.add_middleware(LoggingMiddleware())  # runs first
app.add_middleware(AuthMiddleware())     # runs second
```

## Dependencies

FastAPI-style dependency injection with `Depends()`:

```python
from microapi import Depends, Service, Schema

async def get_database():
    db = await create_connection()
    return db

async def get_current_user():
    return {"id": 1, "name": "admin"}

service = Service("items")

@service.method
async def get_items(
    payload: ItemsPayload,
    db = Depends(get_database),
    user = Depends(get_current_user),
) -> ItemList:
    items = await db.query(user["id"])
    return ItemList(items=items)
```

Dependencies are:
- Resolved per-request
- Cached by default (same dependency reused within a request)
- Support both sync and async callables

## Code Generation

### Python Client Library

```bash
microapi generate server.main:app --output lib
```

Generates:
- `lib/types.py` — Pydantic schemas as client models
- `lib/{service}.py` — Typed async functions and stream classes
- `lib/__init__.py` — Convenience imports

### Protobuf Files

```bash
microapi generate server.main:app --protos --protos-dir protos
```

Generates standard `.proto` files for cross-language gRPC interop:

```protobuf
syntax = "proto3";
package users;

message User {
  optional string username = 1;
  optional string firstname = 2;
  optional int64 age = 3;
}

service UsersService {
  rpc get_user(GetUserPayload) returns (User);
  rpc list_users(ListPayload) returns (stream User);
}
```

## CLI

```bash
# Run a server
microapi run server.main:app --transport http --port 8080 --reload

# Generate client library
microapi generate server.main:app --output lib --protos

# Show service info
microapi info server.main:app

# Scaffold a new project
microapi init myservice

# Print version
microapi version
```

## Lifecycle Hooks

```python
app = MicroAPI()

@app.on_startup
async def startup():
    print("Server starting...")
    await init_database()

@app.on_shutdown
async def shutdown():
    print("Server stopping...")
    await close_connections()
```

Or use a lifespan context manager:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # Startup
    db = await connect_db()
    yield
    # Shutdown
    await db.close()

app = MicroAPI(lifespan=lifespan)
```

## Project Structure

```
microapi/
├── app.py              # MicroAPI application class
├── service.py          # Service & @method decorator
├── schema.py           # Pydantic Schema base class
├── types.py            # Stream, Streaming types
├── middleware.py        # Middleware system
├── dependencies.py     # Depends() injection
├── protocol.py         # Wire protocol messages
├── serialization.py    # JSON serialization (orjson)
├── routing.py          # Request router/dispatcher
├── transport/
│   ├── base.py         # Abstract transport interfaces
│   ├── grpc/           # Custom gRPC (h2-based)
│   ├── http/           # HTTP (aiohttp)
│   ├── websocket/      # WebSocket
│   ├── kafka/          # Apache Kafka
│   └── rabbitmq/       # RabbitMQ
├── client/             # Client SDK base classes
├── generator/          # Code generators (Python + Protobuf)
├── cli/                # CLI tool (typer + rich)
└── hot_reload.py       # File watcher
```

## Configuration

All transports accept simple configuration:

```python
# gRPC with SSL
import ssl
ctx = ssl.create_default_context()
GRPCTransport(host="0.0.0.0", port=50051, ssl_context=ctx)

# HTTP
HTTPTransport(host="0.0.0.0", port=8080)

# WebSocket
WebSocketTransport(host="0.0.0.0", port=8765)

# Kafka
KafkaTransport(
    bootstrap_servers="kafka1:9092,kafka2:9092",
    request_topic="my-requests",
    response_topic="my-responses",
    group_id="my-service",
)

# RabbitMQ
RabbitMQTransport(
    url="amqp://user:pass@rabbitmq:5672/vhost",
    request_queue="my-requests",
    response_queue="my-responses",
)
```

## Development

```bash
# Clone
git clone https://github.com/BiqRed/MicroAPI.git
cd MicroAPI

# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check microapi/

# Type check
uv run mypy microapi/
```

## License

MIT
