# Streaming

MicroAPI supports all four gRPC-style RPC patterns. The pattern is detected automatically from your method's type hints.

## Pattern Detection

MicroAPI inspects the function signature to determine the RPC pattern:

| Pattern | Input | Output | Detection |
|---------|-------|--------|-----------|
| Unary | `payload: T` | `-> R` | No `Stream`/`Streaming` types |
| Server streaming | `payload: T` | `-> Streaming[R]` | Return type is `Streaming[R]` |
| Client streaming | `stream: Stream[T]` | `-> R` | First param is `Stream[T]` |
| Bidirectional | `stream: Stream[T]` | `-> Streaming[R]` | Both `Stream` and `Streaming` |

## Unary (Request → Response)

The simplest pattern. One request, one response.

```python
from microapi import Service, Schema

class GetUserPayload(Schema):
    user_id: int

class User(Schema):
    username: str
    age: int

service = Service("users")

@service.method
async def get_user(payload: GetUserPayload) -> User:
    user = await db.get(payload.user_id)
    return User(username=user.name, age=user.age)
```

**Generated client usage:**

```python
user = await users.get_user(user_id=42)
print(user.username)  # "alice"
print(user.age)       # 30
```

## Server Streaming (Request → Stream of Responses)

The server sends multiple responses for a single request. Use `types.Streaming[T]` as the return type and `yield` each item.

```python
from microapi import Service, Schema, types

class ListPayload(Schema):
    limit: int = 100

class User(Schema):
    username: str
    age: int

service = Service("users")

@service.method
async def list_users(payload: ListPayload) -> types.Streaming[User]:
    """Stream users from the database."""
    async for row in db.query("SELECT * FROM users LIMIT $1", payload.limit):
        yield User(username=row["name"], age=row["age"])
```

**Generated client usage:**

```python
async for user in users.list_users(limit=50):
    print(f"User: {user.username}")
```

### Real-World Examples

**Log streaming:**
```python
@service.method
async def stream_logs(payload: LogFilter) -> types.Streaming[LogEntry]:
    async for line in tail_log_file(payload.path):
        if payload.level and line.level < payload.level:
            continue
        yield LogEntry(timestamp=line.ts, message=line.msg, level=line.level)
```

**Search results with progress:**
```python
@service.method
async def search(payload: SearchQuery) -> types.Streaming[SearchResult]:
    for index in payload.indices:
        async for hit in index.search(payload.query):
            yield SearchResult(index=index.name, doc=hit)
```

## Client Streaming (Stream of Requests → Response)

The client sends a stream of messages, the server processes them and returns a single response. Use `types.Stream[T]` as the input type.

```python
from microapi import Service, Schema, types

class DataPoint(Schema):
    timestamp: float
    value: float

class AggregateResult(Schema):
    count: int
    average: float
    total: float

service = Service("analytics")

@service.method
async def aggregate(stream: types.Stream[DataPoint]) -> AggregateResult:
    """Receive data points and return aggregated statistics."""
    total = 0.0
    count = 0
    async for point in stream:
        total += point.value
        count += 1
    return AggregateResult(
        count=count,
        average=total / count if count > 0 else 0,
        total=total,
    )
```

**Generated client usage:**

```python
# The generated client creates a stream class
stream = analytics.aggregate()
await stream.send(timestamp=1.0, value=10.5)
await stream.send(timestamp=2.0, value=20.3)
await stream.send(timestamp=3.0, value=15.8)
result = await stream.end()  # Sends all buffered data and gets response
print(f"Average: {result}")
```

### How Client Streaming Works

Internally, MicroAPI buffers the `send()` calls on the client side. When `end()` is called, all buffered messages are sent as a JSON array in a single request. On the server side, MicroAPI feeds these into a `Stream` object that your handler consumes with `async for`.

## Bidirectional Streaming (Stream ↔ Stream)

Both client and server stream messages. The server receives a `types.Stream[T]` and returns `types.Streaming[U]`.

```python
from microapi import Service, Schema, types

class ChatMessage(Schema):
    text: str
    user: str

class ChatResponse(Schema):
    reply: str
    source: str

service = Service("chat")

@service.method
async def conversation(stream: types.Stream[ChatMessage]) -> types.Streaming[ChatResponse]:
    """Echo-style chat: receive messages and reply to each one."""
    async for msg in stream:
        reply = await generate_reply(msg.text)
        yield ChatResponse(reply=reply, source=msg.user)
```

**Generated client usage:**

```python
bidi = chat.conversation()
await bidi.send(text="Hello!", user="alice")
response = await bidi.next()
print(response)  # ChatResponse(reply="Hi Alice!", source="alice")

await bidi.send(text="How are you?", user="alice")
response = await bidi.next()
print(response)

await bidi.end()
```

## The Stream Object

`types.Stream[T]` is an async iterable that represents incoming messages:

```python
from microapi.types import Stream

@service.method
async def process(stream: Stream[Item]) -> Result:
    items = []
    async for item in stream:
        items.append(item)
    # Stream is now exhausted
    return Result(count=len(items))
```

### Stream Properties

- **`stream.closed`**: `True` after the stream has been fully consumed
- The stream is an `AsyncIterator` — use it with `async for`
- Reading from a closed stream yields nothing (no error)
- Writing to a closed stream raises `StreamClosedError`

## Generated Client Code

The code generator produces different client constructs for each pattern:

### Unary → Async Function

```python
# Generated: lib/users.py
async def get_user(user_id: int) -> User:
    """Call users.get_user."""
    conn = Connection.get_current()
    result = await conn.request(
        service="users", method="get_user",
        payload={"user_id": user_id},
    )
    return User.model_validate(result)
```

### Server Streaming → Async Generator Function

```python
# Generated: lib/users.py
async def list_users(limit: int = 100) -> AsyncIterator[User]:
    """Stream results from users.list_users."""
    conn = Connection.get_current()
    async for item in conn.request_stream(
        service="users", method="list_users",
        payload={"limit": limit},
    ):
        yield User.model_validate(item)
```

### Client Streaming → Stream Class

```python
# Generated: lib/analytics.py
class aggregate(ClientStream):
    """Client stream for analytics.aggregate."""

    def __init__(self) -> None:
        conn = Connection.get_current()
        super().__init__(service="analytics", method="aggregate", transport=conn.transport)

    async def send(self, timestamp: float, value: float) -> None:
        """Send a message to the server."""
        await self._send_raw(DataPoint(timestamp=timestamp, value=value).model_dump())

    async def end(self) -> None:
        """Signal end of stream."""
        await super().end()
```

### Bidirectional → BiStream Class

```python
# Generated: lib/chat.py
class conversation(ClientStream[ChatResponse]):
    """Bidirectional stream for chat.conversation."""

    def __init__(self) -> None:
        conn = Connection.get_current()
        super().__init__(service="chat", method="conversation", transport=conn.transport)

    async def send(self, text: str, user: str) -> None:
        await self._send_raw(ChatMessage(text=text, user=user).model_dump())

    async def next(self) -> ChatResponse | None:
        data = await super().next()
        if data is not None:
            return ChatResponse.model_validate(data)
        return None

    async def end(self) -> None:
        await super().end()
```
