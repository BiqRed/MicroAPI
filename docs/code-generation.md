# Code Generation

MicroAPI can automatically generate fully-typed Python client libraries and Protobuf `.proto` files from your service definitions. This is one of the core features — it enables calling remote services as if they were local Python functions, with full IDE autocompletion.

## Python Client Library

### Automatic Generation

The simplest way is to enable auto-generation when starting the server:

```python
app.run(
    transport=HTTPTransport(port=8080),
    auto_generate_lib=True,
    generated_lib_dir="lib",
)
```

This generates the client library in the `lib/` directory every time the server starts.

### CLI Generation

Generate without starting the server:

```bash
microapi generate server.main:app --output lib
```

### Programmatic Generation

```python
from microapi.generator import generate_python_lib

generate_python_lib(app.router.services, Path("lib"))
```

### Generated Structure

For a service named `users` with schemas `User` and `GetUserPayload`:

```
lib/
├── __init__.py       # Re-exports all service modules and schema types
├── types.py          # Pydantic schemas as client models
└── users.py          # Typed functions and stream classes
```

### `types.py` — Schema Types

Contains all Pydantic schemas used by your services, converted to client-side models:

```python
"""Auto-generated schema types for MicroAPI client."""

from __future__ import annotations

from microapi.client.base import ClientSchema


class GetUserPayload(ClientSchema):
    user_id: int

class User(ClientSchema):
    username: str
    age: int = 0

__all__ = ['GetUserPayload', 'User']
```

`ClientSchema` is a Pydantic `BaseModel` with `from_attributes=True` and `populate_by_name=True`.

### Service Modules — Typed Client Code

Each service gets its own module with typed functions:

```python
"""Auto-generated client for the "users" service."""

from __future__ import annotations

from collections.abc import AsyncIterator

from microapi.client.base import Connection

from .types import GetUserPayload, User


async def get_user(user_id: int) -> User:
    """Call users.get_user."""
    conn = Connection.get_current()
    result = await conn.request(
        service="users",
        method="get_user",
        payload={"user_id": user_id},
    )
    return User.model_validate(result)

async def list_users(user_id: int) -> AsyncIterator[User]:
    """Stream results from users.list_users."""
    conn = Connection.get_current()
    async for item in conn.request_stream(
        service="users",
        method="list_users",
        payload={"user_id": user_id},
    ):
        yield User.model_validate(item)

__all__ = ['get_user', 'list_users']
```

Key properties of generated code:
- **Explicit imports** — no star imports, every type is explicitly imported
- **Full type annotations** — parameters, return types, all typed
- **Docstrings** — each function documents which service/method it calls
- **`__all__` exports** — proper module exports for clean namespaces
- **`from __future__ import annotations`** — forward references work

### `__init__.py` — Convenience Re-exports

```python
"""Auto-generated MicroAPI client library."""

from __future__ import annotations

from . import users
from .types import *  # noqa: F403

__all__ = ['users', 'GetUserPayload', 'User']
```

This allows both:
```python
from lib import users
user = await users.get_user(user_id=1)

# and
from lib import User
print(User(username="alice", age=30))
```

### Using the Generated Client

```python
import asyncio
from lib import users
from microapi.client.base import Connection
from microapi.transport.http import HTTPTransport

async def main():
    transport = HTTPTransport(host="127.0.0.1", port=8080)
    conn = Connection(transport.create_client())

    async with conn:
        # Unary call
        user = await users.get_user(user_id=1)
        print(user.username)

        # Server streaming
        async for user in users.list_users(user_id=0):
            print(user)

asyncio.run(main())
```

### Type Mapping

The generator maps Python/Pydantic types to their string representations:

| Python Type | Generated |
|-------------|-----------|
| `str` | `str` |
| `int` | `int` |
| `float` | `float` |
| `bool` | `bool` |
| `bytes` | `bytes` |
| `None` | `None` |
| `list[str]` | `list[str]` |
| `dict[str, int]` | `dict[str, int]` |
| `set[int]` | `set[int]` |
| `tuple[str, int]` | `tuple[str, int]` |
| `str \| None` | `str \| None` |
| `MyModel` | `MyModel` |

---

## Protobuf Generation

Generate `.proto` files for cross-language gRPC interop:

### Automatic Generation

```python
app.run(
    transport=GRPCTransport(port=50051),
    generate_protos=True,
    protos_dir="protos",
)
```

### CLI Generation

```bash
microapi generate server.main:app --protos --protos-dir protos
```

### Programmatic Generation

```python
from microapi.generator import generate_proto_files

generate_proto_files(app.router.services, Path("protos"))
```

### Generated Proto Files

For each service, a `.proto` file is created:

```protobuf
syntax = "proto3";
package users;

message User {
    optional string username = 1;
    optional int64 age = 2;
}

message GetUserPayload {
    int64 user_id = 1;
    repeated string fields = 2;
}

service UsersService {
    rpc get_user(GetUserPayload) returns (User);
    rpc list_users(GetUserPayload) returns (stream User);
    rpc add_users(stream User) returns (google.protobuf.Empty);
    rpc chat(stream ChatMessage) returns (stream ChatResponse);
}
```

### Proto Type Mapping

| Python Type | Protobuf Type |
|-------------|---------------|
| `str` | `string` |
| `int` | `int64` |
| `float` | `double` |
| `bool` | `bool` |
| `bytes` | `bytes` |
| `list[T]` | `repeated T` |
| `T \| None` | `optional T` |

### Using Generated Protos

Use the generated `.proto` files with any gRPC toolchain:

```bash
# Python (grpcio-tools)
python -m grpc_tools.protoc -I protos --python_out=. --grpc_python_out=. protos/users.proto

# Go
protoc --go_out=. --go-grpc_out=. protos/users.proto

# TypeScript (ts-proto)
protoc --plugin=protoc-gen-ts_proto --ts_proto_out=. protos/users.proto
```

## Customizing Generated Names

By default, generated function/class names match the Python function name. Override with `generated_name`:

```python
@service.method(generated_name="create_return_user")
async def add_and_get_users(stream: Stream[User]) -> Streaming[User]:
    ...
```

In the generated client:
```python
# Uses the custom name
bidi = users.create_return_user()
```
