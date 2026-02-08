# Dependency Injection

MicroAPI supports FastAPI-style dependency injection via `Depends()`. Dependencies are resolved per-request, cached within the same request, and support both sync and async callables.

## Basic Usage

```python
from microapi import Depends, Service, Schema

async def get_database():
    """Provide a database connection."""
    return await create_db_connection()

service = Service("items")

@service.method
async def get_items(
    payload: ItemQuery,
    db = Depends(get_database),
) -> ItemList:
    items = await db.query(payload.filter)
    return ItemList(items=items)
```

When `get_items` is called, MicroAPI will:
1. Call `get_database()` to resolve the dependency
2. Pass the result as the `db` parameter
3. Execute the handler

## How It Works

`Depends(callable)` is a sentinel marker. When MicroAPI sees a parameter with a `Depends` default value, it:

1. Calls the dependency function
2. Caches the result for the current request
3. Injects the result into the handler

Dependencies are resolved **before** the handler is called.

## Async Dependencies

Dependencies can be either sync or async:

```python
# Async dependency
async def get_database():
    return await Database.connect()

# Sync dependency
def get_config():
    return {"version": "1.0", "debug": True}

@service.method
async def my_method(
    payload: Payload,
    db = Depends(get_database),       # async
    config = Depends(get_config),     # sync
) -> Result:
    ...
```

## Accessing the Request

Dependencies can receive the current `Request` object by type-hinting a parameter:

```python
from microapi.protocol import Request

async def get_current_user(req: Request) -> dict:
    """Extract user info from request metadata."""
    user_id = req.metadata.get("user_id")
    if not user_id:
        raise ValueError("No user_id in metadata")
    return {"id": user_id, "role": req.metadata.get("role", "user")}

@service.method
async def protected_action(
    payload: ActionPayload,
    user = Depends(get_current_user),
) -> ActionResult:
    if user["role"] != "admin":
        raise PermissionError("Admin only")
    ...
```

This is especially powerful combined with middleware that sets metadata:

```python
# Middleware sets user info
class AuthMiddleware(Middleware):
    async def __call__(self, request, call_next):
        token = request.metadata.get("authorization")
        user = await verify_token(token)
        request.metadata["user_id"] = str(user.id)
        request.metadata["role"] = user.role
        return await call_next(request)

# Dependency reads it
async def get_current_user(req: Request) -> dict:
    return {
        "id": req.metadata["user_id"],
        "role": req.metadata["role"],
    }
```

## Dependency Caching

Dependencies are cached within a single request. If multiple parameters depend on the same function, it's called only once:

```python
async def get_database():
    print("Connecting to database...")  # Printed only once per request
    return await Database.connect()

@service.method
async def handler(
    payload: Payload,
    db1 = Depends(get_database),
    db2 = Depends(get_database),  # Same instance as db1
) -> Result:
    assert db1 is db2  # True!
    ...
```

## Nested Dependencies

Dependencies can themselves have dependencies:

```python
async def get_config():
    return load_config()

async def get_database(config = Depends(get_config)):
    return await Database.connect(config["db_url"])

async def get_user_repo(db = Depends(get_database)):
    return UserRepository(db)

@service.method
async def get_user(
    payload: GetUserPayload,
    repo = Depends(get_user_repo),
) -> User:
    return await repo.get(payload.user_id)
```

Resolution order: `get_config` → `get_database` → `get_user_repo` → handler.

## Class-Based Dependencies

You can use callable classes as dependencies:

```python
class DatabasePool:
    def __init__(self, connection_string: str):
        self.conn_str = connection_string
        self.pool = None

    async def __call__(self):
        if not self.pool:
            self.pool = await create_pool(self.conn_str)
        return self.pool

# Create an instance
db_pool = DatabasePool("postgresql://localhost/mydb")

@service.method
async def query(
    payload: QueryPayload,
    pool = Depends(db_pool),
) -> QueryResult:
    async with pool.acquire() as conn:
        ...
```

## Pattern: Repository Layer

A common pattern is to create a repository layer using dependencies:

```python
# repositories.py
from microapi import Depends
from microapi.protocol import Request

async def get_db():
    return await create_connection()

class UserRepository:
    def __init__(self, db):
        self.db = db

    async def get(self, user_id: int) -> User | None:
        row = await self.db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return User(**row) if row else None

    async def create(self, data: dict) -> User:
        row = await self.db.fetchrow(
            "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *",
            data["name"], data["email"],
        )
        return User(**row)

async def get_user_repo(db = Depends(get_db)) -> UserRepository:
    return UserRepository(db)

# service.py
@service.method
async def get_user(
    payload: GetUserPayload,
    repo: UserRepository = Depends(get_user_repo),
) -> User:
    user = await repo.get(payload.user_id)
    if not user:
        raise NotFoundError(f"User {payload.user_id} not found")
    return user
```

## Limitations

- Dependencies are resolved per-request (no singleton/app-level scope)
- Generator dependencies (with `yield`) are not yet supported — use lifespan hooks for setup/teardown
- Dependencies don't have access to the raw transport-level connection
