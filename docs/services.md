# Services & Methods

Services are the core building block of MicroAPI. A service groups related RPC methods under a common name.

## Defining a Service

```python
from microapi import Service

service = Service("users")
```

The service name (`"users"`) is used in routing — clients call `users.get_user(...)` to reach the `get_user` method on the `users` service.

## Registering Methods

Use the `@service.method` decorator to register async functions as RPC methods:

```python
@service.method
async def get_user(payload: GetUserPayload) -> User:
    return User(username="alice", age=30)
```

The decorator can also accept arguments:

```python
@service.method(generated_name="fetch_user")
async def get_user(payload: GetUserPayload) -> User:
    ...
```

- **`generated_name`**: Override the function name used in the generated client library. By default, the function name is used.

## Method Signatures

MicroAPI detects the RPC pattern automatically from the method's type hints:

### Unary (Request → Response)

A regular async function with a Pydantic payload and a return type:

```python
@service.method
async def get_user(payload: GetUserPayload) -> User:
    user = await db.get(payload.user_id)
    return User.model_validate(user)
```

### No Input

Methods can omit the payload parameter entirely:

```python
@service.method
async def health_check() -> HealthStatus:
    return HealthStatus(ok=True)
```

### None Return

Methods can return `None`:

```python
@service.method
async def delete_user(payload: DeletePayload) -> None:
    await db.delete(payload.user_id)
```

### Server Streaming (Request → Stream of Responses)

Return `types.Streaming[T]` to stream multiple responses:

```python
from microapi import types

@service.method
async def list_users(payload: ListPayload) -> types.Streaming[User]:
    users = await db.get_all(limit=payload.limit)
    for user in users:
        yield User.model_validate(user)
```

The method is an async generator that yields items one at a time. The transport handles sending each item to the client.

### Client Streaming (Stream of Requests → Response)

Accept `types.Stream[T]` to receive a stream of messages from the client:

```python
from microapi import types

@service.method
async def bulk_create(stream: types.Stream[User]) -> CreateResult:
    count = 0
    async for user in stream:
        await db.save(user)
        count += 1
    return CreateResult(created=count)
```

`Stream[T]` is an async iterable — use `async for` to consume incoming messages.

### Bidirectional Streaming (Stream ↔ Stream)

Combine `types.Stream[T]` input with `types.Streaming[U]` output:

```python
@service.method
async def chat(stream: types.Stream[ChatMessage]) -> types.Streaming[ChatResponse]:
    async for msg in stream:
        reply = await process_message(msg.text)
        yield ChatResponse(reply=reply)
```

## Schemas

Schemas are Pydantic models that define the data contract. Use `Schema` (alias for a configured `BaseModel`):

```python
from microapi import Schema

class User(Schema):
    username: str
    email: str
    age: int | None = None
    tags: list[str] = []
```

`Schema` adds these Pydantic config options:
- `from_attributes=True` — allows creating from ORM objects
- `populate_by_name=True` — supports both field names and aliases

### Supported Types

All Pydantic-supported types work:

```python
class ComplexSchema(Schema):
    # Primitives
    name: str
    count: int
    score: float
    active: bool

    # Optional
    bio: str | None = None

    # Collections
    tags: list[str] = []
    metadata: dict[str, str] = {}
    unique_ids: set[int] = set()

    # Nested models
    address: Address | None = None
    orders: list[Order] = []
```

## Registering Services with the Application

```python
from microapi import MicroAPI

app = MicroAPI()

# Register one at a time
app.add_service(users_service)
app.add_service(orders_service)

# Or pass at construction
app = MicroAPI(services=[users_service, orders_service])
```

## Multiple Services

An application can have multiple services:

```python
users_service = Service("users")
orders_service = Service("orders")
notifications_service = Service("notifications")

@users_service.method
async def get_user(payload: GetUserPayload) -> User: ...

@orders_service.method
async def create_order(payload: CreateOrderPayload) -> Order: ...

@notifications_service.method
async def send_notification(payload: NotifyPayload) -> None: ...

app = MicroAPI(services=[users_service, orders_service, notifications_service])
```

Each service becomes a separate module in the generated client library.

## Error Handling

Exceptions raised in methods are caught and returned as error responses:

```python
from microapi.exceptions import NotFoundError, ValidationError

@service.method
async def get_user(payload: GetUserPayload) -> User:
    user = await db.get(payload.user_id)
    if not user:
        raise NotFoundError(f"User {payload.user_id} not found")
    return user
```

Built-in exception types:
- `MicroAPIError` — base exception
- `NotFoundError` — resource not found (maps to `NOT_FOUND` status)
- `ValidationError` — invalid input (maps to `INVALID_ARGUMENT`)
- `TransportError` — transport-level errors
- `StreamClosedError` — writing to a closed stream

Standard Python exceptions (`ValueError`, `RuntimeError`, etc.) are caught and returned as `INTERNAL` errors.
