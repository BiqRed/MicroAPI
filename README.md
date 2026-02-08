# MicroAPI

[![PyPI version](https://img.shields.io/pypi/v/microapi.svg)](https://pypi.org/project/microapi/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

**MicroAPI** is a Python microservices framework that lets your services communicate as if calling regular Python functions. Built with a **FastAPI-like** interface, full **Pydantic** typing, and multiple transport backends.

```python
from microapi import MicroAPI, Service, Schema
from microapi.transport.http import HTTPTransport

class User(Schema):
    username: str
    age: int = 0

service = Service("users")

@service.method
async def get_user(payload: GetUserPayload) -> User:
    return User(username="alice", age=30)

app = MicroAPI(services=[service])
app.run(transport=HTTPTransport(port=8080), auto_generate_lib=True)
```

On the client side, the auto-generated library gives you **full IDE autocompletion**:

```python
from lib import users
from microapi.client.base import Connection
from microapi.transport.http import HTTPTransport

async with Connection(HTTPTransport(port=8080).create_client()) as conn:
    user = await users.get_user(user_id=1)   # fully typed!
    print(user.username)                       # IDE knows this is str
```

## Key Features

| Feature | Description |
|---------|-------------|
| **FastAPI-like Interface** | `@service.method` decorator, Pydantic schemas, dependency injection |
| **5 Transports** | gRPC (custom h2), HTTP, WebSocket, Kafka, RabbitMQ |
| **4 RPC Patterns** | Unary, server streaming, client streaming, bidirectional |
| **Auto Code Generation** | Typed Python client libraries + `.proto` files |
| **Middleware** | Composable middleware chain with full request/response access |
| **Dependency Injection** | `Depends()` with caching, async support, request access |
| **CLI Tool** | `microapi run`, `microapi generate`, `microapi init`, `microapi info` |
| **Hot Reload** | Auto-restart on file changes during development |
| **Type Safe** | Full Pydantic validation + generated client code with type hints |

## Installation

```bash
pip install microapi            # Core framework
pip install microapi[http]      # + HTTP transport (aiohttp)
pip install microapi[grpc]      # + gRPC transport (h2-based)
pip install microapi[ws]        # + WebSocket transport
pip install microapi[kafka]     # + Apache Kafka transport
pip install microapi[rabbitmq]  # + RabbitMQ transport
pip install microapi[all]       # Everything
```

## Quick Start

See the full [Getting Started Guide](docs/getting-started.md) for a complete walkthrough.

### 1. Define schemas and a service

```python
# schemas.py
from microapi import Schema

class UserPayload(Schema):
    user_id: int

class User(Schema):
    username: str
    age: int = 0
```

```python
# service.py
from microapi import Service, types
from schemas import UserPayload, User

service = Service("users")

@service.method
async def get_user(payload: UserPayload) -> User:
    return User(username="alice", age=30)

@service.method
async def list_users(payload: UserPayload) -> types.Streaming[User]:
    for user in await fetch_all_users():
        yield user
```

### 2. Run the server

```python
# main.py
from microapi import MicroAPI
from microapi.transport.http import HTTPTransport
from service import service

app = MicroAPI(services=[service])
app.run(
    transport=HTTPTransport(host="0.0.0.0", port=8080),
    auto_generate_lib=True,
    generated_lib_dir="lib",
)
```

### 3. Use the auto-generated client

```python
import asyncio
from lib import users
from microapi.client.base import Connection
from microapi.transport.http import HTTPTransport

async def main():
    transport = HTTPTransport(host="127.0.0.1", port=8080)
    async with Connection(transport.create_client()) as conn:
        user = await users.get_user(user_id=1)
        print(user.username)  # IDE autocomplete works!

asyncio.run(main())
```

## Documentation

| Page | Description |
|------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, first project, step-by-step tutorial |
| [Services & Methods](docs/services.md) | Defining services, method patterns, schemas |
| [Transports](docs/transports.md) | HTTP, gRPC, WebSocket, Kafka, RabbitMQ configuration |
| [Streaming](docs/streaming.md) | All 4 RPC patterns with detailed examples |
| [Middleware](docs/middleware.md) | Middleware chain, ordering, short-circuiting |
| [Dependencies](docs/dependencies.md) | `Depends()`, caching, request access, async deps |
| [Code Generation](docs/code-generation.md) | Python client library + Protobuf generation |
| [CLI Reference](docs/cli.md) | All CLI commands and options |
| [Lifecycle](docs/lifecycle.md) | Startup/shutdown hooks, lifespan context managers |
| [Architecture](docs/architecture.md) | Wire protocol, design decisions, project structure |
| [API Reference](docs/api-reference.md) | All public classes, methods, and types |
| [Examples](docs/examples.md) | Complete working examples for all features |

## RPC Patterns at a Glance

```python
# Unary: request → response
@service.method
async def get_user(payload: GetUserPayload) -> User: ...

# Server streaming: request → stream of responses
@service.method
async def list_users(payload: ListPayload) -> types.Streaming[User]: ...

# Client streaming: stream of requests → response
@service.method
async def add_users(stream: types.Stream[User]) -> Result: ...

# Bidirectional: stream ↔ stream
@service.method
async def chat(stream: types.Stream[Message]) -> types.Streaming[Reply]: ...
```

## Transport Comparison

| Transport | Protocol | Streaming | Latency | Use Case |
|-----------|----------|-----------|---------|----------|
| **gRPC** | HTTP/2 | Full | Low | Internal microservices |
| **HTTP** | HTTP/1.1 | Server only | Medium | REST-like APIs, web clients |
| **WebSocket** | WS | Full | Low | Real-time, persistent connections |
| **Kafka** | TCP | Server | High | Event-driven, high throughput |
| **RabbitMQ** | AMQP | Server | Medium | Task queues, reliable delivery |

## Development

```bash
git clone https://github.com/BiqRed/MicroAPI.git
cd MicroAPI
uv sync --all-extras
uv run pytest tests/ -v       # Run tests
uv run ruff check microapi/   # Lint
uv run mypy microapi/         # Type check
```

## License

MIT
