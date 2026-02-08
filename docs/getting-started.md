# Getting Started

This guide walks you through installing MicroAPI, creating your first service, running a server, and making calls from a client.

## Prerequisites

- **Python 3.12+** (MicroAPI uses modern type hints syntax like `X | Y`)
- **pip** or **uv** for package management

## Installation

### With pip

```bash
# Core framework (required)
pip install microapi

# Add the transport(s) you need
pip install microapi[http]       # HTTP transport (aiohttp)
pip install microapi[grpc]       # gRPC transport (custom h2-based)
pip install microapi[ws]         # WebSocket transport
pip install microapi[kafka]      # Apache Kafka transport
pip install microapi[rabbitmq]   # RabbitMQ transport

# Or install everything
pip install microapi[all]
```

### With uv

```bash
uv add microapi
uv add microapi --extra http    # with HTTP transport
uv add microapi --extra all     # everything
```

## Project Structure

A typical MicroAPI project looks like this:

```
my-service/
├── server/
│   ├── main.py          # Application entry point
│   ├── schemas.py       # Pydantic schemas
│   ├── service.py       # Service definitions
│   └── middleware.py     # Optional middleware
├── client/
│   ├── main.py          # Client code
│   └── ...
├── lib/                 # Auto-generated client library
│   ├── __init__.py
│   ├── types.py
│   └── users.py
└── pyproject.toml
```

## Step 1: Define Your Schemas

Schemas are Pydantic models that define the structure of your data. They're used for both validation and type generation.

```python
# server/schemas.py
from microapi import Schema

class CreateUserPayload(Schema):
    username: str
    email: str
    age: int | None = None

class User(Schema):
    id: int
    username: str
    email: str
    age: int | None = None

class GetUserPayload(Schema):
    user_id: int
```

`Schema` is a Pydantic `BaseModel` with extra config (`from_attributes=True`, `populate_by_name=True`), making it easy to convert from ORMs, dicts, and other sources.

## Step 2: Define Your Service

A service groups related RPC methods. Each method is an async function decorated with `@service.method`:

```python
# server/service.py
from microapi import Service
from schemas import CreateUserPayload, GetUserPayload, User

service = Service("users")

# In-memory store for this example
users_db: dict[int, User] = {}
next_id = 1

@service.method
async def create_user(payload: CreateUserPayload) -> User:
    """Create a new user."""
    global next_id
    user = User(id=next_id, username=payload.username, email=payload.email, age=payload.age)
    users_db[next_id] = user
    next_id += 1
    return user

@service.method
async def get_user(payload: GetUserPayload) -> User:
    """Get a user by ID."""
    user = users_db.get(payload.user_id)
    if not user:
        raise ValueError(f"User {payload.user_id} not found")
    return user
```

**Key points:**
- The method's first parameter (`payload`) is automatically validated against its type annotation
- The return type annotation determines the response schema
- RPC pattern (unary, streaming, etc.) is detected from type hints
- Exceptions are caught and returned as error responses

## Step 3: Create and Run the Application

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
        auto_generate_lib=True,          # Generate client library on startup
        generated_lib_dir="../lib",       # Where to put generated code
        log_level="INFO",
    )
```

When you run this, MicroAPI will:
1. Generate a typed client library in `../lib/`
2. Start the HTTP server on `0.0.0.0:8080`
3. Log that the server is ready

```bash
$ python server/main.py
2026-02-08 12:00:00 | INFO | microapi.generator | Generated client library: 1 service(s), 3 schema(s) -> ../lib
2026-02-08 12:00:00 | INFO | microapi | Generated client library in ../lib
2026-02-08 12:00:00 | INFO | microapi | MicroAPI server started
```

## Step 4: Use the Generated Client

The auto-generated `lib/` directory contains fully-typed Python modules:

```python
# client/main.py
import asyncio
import sys
sys.path.insert(0, "..")  # so we can import lib/

from lib import users
from microapi.client.base import Connection
from microapi.transport.http import HTTPTransport

async def main():
    transport = HTTPTransport(host="127.0.0.1", port=8080)
    conn = Connection(transport.create_client())

    async with conn:
        # Create a user — fully typed parameters!
        user = await users.create_user(
            username="alice",
            email="alice@example.com",
            age=30,
        )
        print(f"Created: {user}")   # user is a typed User object

        # Get a user
        fetched = await users.get_user(user_id=user.id)
        print(f"Fetched: {fetched.username}")  # IDE knows this is str

asyncio.run(main())
```

## Step 5: Use the CLI (Optional)

MicroAPI includes a CLI tool for common tasks:

```bash
# Run the server
microapi run server.main:app --transport http --port 8080

# Run with hot reload (auto-restart on code changes)
microapi run server.main:app --transport http --port 8080 --reload

# Generate client library without starting the server
microapi generate server.main:app --output lib

# Generate protobuf files
microapi generate server.main:app --protos --protos-dir protos

# View service information
microapi info server.main:app

# Scaffold a new project
microapi init my_service
```

## Using Different Transports

Switching transports is a one-line change:

```python
# HTTP
from microapi.transport.http import HTTPTransport
app.run(transport=HTTPTransport(port=8080))

# gRPC
from microapi.transport.grpc import GRPCTransport
app.run(transport=GRPCTransport(port=50051))

# WebSocket
from microapi.transport.websocket import WebSocketTransport
app.run(transport=WebSocketTransport(port=8765))
```

The generated client library works with **any** transport — just change the client connection:

```python
# Client connects via HTTP
conn = Connection(HTTPTransport(port=8080).create_client())

# Or via gRPC
conn = Connection(GRPCTransport(port=50051).create_client())

# Or via WebSocket
conn = Connection(WebSocketTransport(port=8765).create_client())
```

## What's Next?

- [Services & Methods](services.md) — Learn about all 4 RPC patterns
- [Transports](transports.md) — Configure each transport in detail
- [Middleware](middleware.md) — Add auth, logging, and more
- [Dependencies](dependencies.md) — FastAPI-style dependency injection
- [Code Generation](code-generation.md) — Customize generated code
- [Examples](examples.md) — Complete working examples
