# Examples

Complete working examples demonstrating all MicroAPI features.

## Basic HTTP Service

A minimal example with one service and the HTTP transport.

### Server

```python
# server.py
from microapi import MicroAPI, Service, Schema
from microapi.transport.http import HTTPTransport


class GreetPayload(Schema):
    name: str

class Greeting(Schema):
    message: str


service = Service("greeter")

@service.method
async def greet(payload: GreetPayload) -> Greeting:
    return Greeting(message=f"Hello, {payload.name}!")


app = MicroAPI(services=[service])

if __name__ == "__main__":
    app.run(
        transport=HTTPTransport(host="0.0.0.0", port=8080),
        auto_generate_lib=True,
        generated_lib_dir="lib",
    )
```

### Client

```python
# client.py
import asyncio
from lib import greeter
from microapi.client.base import Connection
from microapi.transport.http import HTTPTransport


async def main():
    transport = HTTPTransport(host="127.0.0.1", port=8080)
    async with Connection(transport.create_client()) as conn:
        result = await greeter.greet(name="World")
        print(result.message)  # "Hello, World!"


asyncio.run(main())
```

---

## gRPC Service with Protobuf

Using the gRPC transport with automatic `.proto` file generation.

### Server

```python
# server.py
from microapi import MicroAPI, Service, Schema, types
from microapi.transport.grpc import GRPCTransport


class User(Schema):
    username: str
    email: str
    age: int | None = None

class GetUserPayload(Schema):
    user_id: int

class ListUsersPayload(Schema):
    limit: int = 100


service = Service("users")

@service.method
async def get_user(payload: GetUserPayload) -> User:
    return User(username="alice", email="alice@example.com", age=30)

@service.method
async def list_users(payload: ListUsersPayload) -> types.Streaming[User]:
    users = [
        User(username="alice", email="alice@example.com", age=30),
        User(username="bob", email="bob@example.com", age=25),
        User(username="charlie", email="charlie@example.com", age=35),
    ]
    for user in users[:payload.limit]:
        yield user


app = MicroAPI(services=[service])

if __name__ == "__main__":
    app.run(
        transport=GRPCTransport(host="0.0.0.0", port=50051),
        auto_generate_lib=True,
        generated_lib_dir="lib",
        generate_protos=True,
        protos_dir="protos",
    )
```

### Client

```python
# client.py
import asyncio
from lib import users
from microapi.client.base import Connection
from microapi.transport.grpc import GRPCTransport


async def main():
    transport = GRPCTransport(host="127.0.0.1", port=50051)
    async with Connection(transport.create_client()) as conn:
        # Unary call
        user = await users.get_user(user_id=1)
        print(f"User: {user.username} ({user.email})")

        # Server streaming
        print("\nAll users:")
        async for user in users.list_users(limit=10):
            print(f"  - {user.username}, age {user.age}")


asyncio.run(main())
```

---

## All 4 Streaming Patterns

A complete example demonstrating all RPC patterns.

### Server

```python
# server.py
from microapi import MicroAPI, Service, Schema, types
from microapi.transport.websocket import WebSocketTransport


class NumberPayload(Schema):
    value: int

class NumberResult(Schema):
    result: int

class ChatMessage(Schema):
    text: str
    user: str

class ChatResponse(Schema):
    reply: str


service = Service("demo")

# 1. Unary: single request, single response
@service.method
async def square(payload: NumberPayload) -> NumberResult:
    return NumberResult(result=payload.value ** 2)

# 2. Server streaming: single request, stream of responses
@service.method
async def count_up(payload: NumberPayload) -> types.Streaming[NumberResult]:
    for i in range(payload.value):
        yield NumberResult(result=i)

# 3. Client streaming: stream of requests, single response
@service.method
async def sum_numbers(stream: types.Stream[NumberPayload]) -> NumberResult:
    total = 0
    async for item in stream:
        total += item.value
    return NumberResult(result=total)

# 4. Bidirectional streaming: stream of requests ↔ stream of responses
@service.method
async def chat(stream: types.Stream[ChatMessage]) -> types.Streaming[ChatResponse]:
    async for msg in stream:
        yield ChatResponse(reply=f"Echo from {msg.user}: {msg.text}")


app = MicroAPI(services=[service])

if __name__ == "__main__":
    app.run(
        transport=WebSocketTransport(host="0.0.0.0", port=8765),
        auto_generate_lib=True,
    )
```

### Client

```python
# client.py
import asyncio
from lib import demo
from microapi.client.base import Connection
from microapi.transport.websocket import WebSocketTransport


async def main():
    transport = WebSocketTransport(host="127.0.0.1", port=8765)
    async with Connection(transport.create_client()) as conn:

        # 1. Unary
        print("=== Unary ===")
        result = await demo.square(value=7)
        print(f"7² = {result.result}")

        # 2. Server streaming
        print("\n=== Server Streaming ===")
        async for num in demo.count_up(value=5):
            print(f"  Count: {num.result}")

        # 3. Client streaming
        print("\n=== Client Streaming ===")
        stream = demo.sum_numbers()
        await stream.send(value=10)
        await stream.send(value=20)
        await stream.send(value=30)
        result = await stream.end()
        print(f"  Sum: {result}")

        # 4. Bidirectional streaming
        print("\n=== Bidi Streaming ===")
        bidi = demo.chat()
        await bidi.send(text="Hello!", user="alice")
        reply = await bidi.next()
        print(f"  {reply}")
        await bidi.send(text="How are you?", user="alice")
        reply = await bidi.next()
        print(f"  {reply}")
        await bidi.end()


asyncio.run(main())
```

---

## Middleware + Auth + Dependencies

A production-like example combining middleware, authentication, and dependency injection.

### Server

```python
# server.py
import hashlib
from microapi import MicroAPI, Service, Schema, Depends, Middleware
from microapi.protocol import Request, Response, StatusCode
from microapi.transport.http import HTTPTransport


# --- Schemas ---

class LoginPayload(Schema):
    username: str
    password: str

class TokenResult(Schema):
    token: str

class ProfilePayload(Schema):
    fields: list[str] | None = None

class UserProfile(Schema):
    username: str
    email: str
    role: str


# --- Fake database ---

USERS = {
    "alice": {"password": "secret", "email": "alice@example.com", "role": "admin"},
    "bob": {"password": "12345", "email": "bob@example.com", "role": "user"},
}
TOKENS: dict[str, str] = {}  # token -> username


# --- Middleware ---

class LoggingMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        print(f"→ {request.service}.{request.method} [{request.id[:8]}]")
        response = await call_next(request)
        print(f"← {response.status_code.name} [{request.id[:8]}]")
        return response


class AuthMiddleware(Middleware):
    async def __call__(self, request: Request, call_next) -> Response:
        # Skip auth for login
        if request.method == "login":
            return await call_next(request)

        token = request.metadata.get("authorization", "").removeprefix("Bearer ")
        username = TOKENS.get(token)
        if not username:
            return Response(
                error="Invalid or missing token",
                status_code=StatusCode.UNAUTHENTICATED,
            )

        # Set user info for dependencies
        request.metadata["username"] = username
        request.metadata["role"] = USERS[username]["role"]
        return await call_next(request)


# --- Dependencies ---

async def get_current_user(req: Request) -> dict:
    username = req.metadata.get("username", "anonymous")
    return USERS.get(username, {})


# --- Service ---

auth_service = Service("auth")

@auth_service.method
async def login(payload: LoginPayload) -> TokenResult:
    user = USERS.get(payload.username)
    if not user or user["password"] != payload.password:
        raise ValueError("Invalid credentials")

    token = hashlib.sha256(f"{payload.username}:{payload.password}".encode()).hexdigest()[:32]
    TOKENS[token] = payload.username
    return TokenResult(token=token)


@auth_service.method
async def get_profile(
    payload: ProfilePayload,
    user: dict = Depends(get_current_user),
) -> UserProfile:
    return UserProfile(
        username=user.get("email", "unknown").split("@")[0],
        email=user.get("email", "unknown"),
        role=user.get("role", "user"),
    )


# --- App ---

app = MicroAPI(
    services=[auth_service],
    middlewares=[LoggingMiddleware(), AuthMiddleware()],
)

if __name__ == "__main__":
    app.run(
        transport=HTTPTransport(port=8080),
        auto_generate_lib=True,
    )
```

### Client

```python
# client.py
import asyncio
from microapi.client.base import Connection
from microapi.transport.http import HTTPTransport


async def main():
    transport = HTTPTransport(host="127.0.0.1", port=8080)
    client = transport.create_client()
    await client.connect()

    # Login (no auth needed)
    token_resp = await client.request("auth", "login", {
        "username": "alice",
        "password": "secret",
    })
    token = token_resp["token"]
    print(f"Got token: {token}")

    # Get profile (with auth)
    profile = await client.request(
        "auth", "get_profile",
        payload={"fields": ["email"]},
        metadata={"authorization": f"Bearer {token}"},
    )
    print(f"Profile: {profile}")

    await client.close()


asyncio.run(main())
```

---

## Lifespan with Database

Using lifespan to manage a database connection pool.

```python
from contextlib import asynccontextmanager
from microapi import MicroAPI, Service, Schema
from microapi.transport.http import HTTPTransport


@asynccontextmanager
async def lifespan(app):
    # Startup: create connection pool
    print("Connecting to database...")
    # app.state can be used to store shared resources
    # db = await asyncpg.create_pool("postgresql://localhost/mydb")
    yield
    # Shutdown: close pool
    print("Closing database connection...")
    # await db.close()


class ItemPayload(Schema):
    name: str

class Item(Schema):
    id: int
    name: str


service = Service("items")

@service.method
async def create_item(payload: ItemPayload) -> Item:
    # In real app: async with db.acquire() as conn: ...
    return Item(id=1, name=payload.name)


app = MicroAPI(services=[service], lifespan=lifespan)

if __name__ == "__main__":
    app.run(transport=HTTPTransport(port=8080))
```

---

## Multiple Services

Running multiple services in a single application.

```python
from microapi import MicroAPI, Service, Schema
from microapi.transport.http import HTTPTransport


# --- Users service ---

class User(Schema):
    id: int
    name: str

class GetUserPayload(Schema):
    user_id: int

users_service = Service("users")

@users_service.method
async def get_user(payload: GetUserPayload) -> User:
    return User(id=payload.user_id, name="Alice")


# --- Orders service ---

class Order(Schema):
    id: int
    user_id: int
    total: float

class GetOrderPayload(Schema):
    order_id: int

orders_service = Service("orders")

@orders_service.method
async def get_order(payload: GetOrderPayload) -> Order:
    return Order(id=payload.order_id, user_id=1, total=99.99)


# --- Notifications service ---

class Notification(Schema):
    message: str

class NotifyPayload(Schema):
    user_id: int
    text: str

notifications_service = Service("notifications")

@notifications_service.method
async def send_notification(payload: NotifyPayload) -> Notification:
    return Notification(message=f"Sent to user {payload.user_id}: {payload.text}")


# --- App with all services ---

app = MicroAPI(services=[
    users_service,
    orders_service,
    notifications_service,
])

if __name__ == "__main__":
    app.run(
        transport=HTTPTransport(port=8080),
        auto_generate_lib=True,
    )
```

This generates:
```
lib/
├── __init__.py
├── types.py           # User, Order, Notification, etc.
├── users.py           # users.get_user()
├── orders.py          # orders.get_order()
└── notifications.py   # notifications.send_notification()
```

---

## CLI Usage

### Scaffold a project

```bash
$ microapi init my_service
Created project: my_service/
```

### Run with hot reload

```bash
$ microapi run server.main:app --transport http --port 8080 --reload --generate-lib
```

### Generate client library and protos

```bash
$ microapi generate server.main:app --output shared/lib --protos --protos-dir shared/protos
Generated Python client library: 3 service(s) -> shared/lib
Generated .proto files: 3 service(s) -> shared/protos
```

### Inspect services

```bash
$ microapi info server.main:app
```
