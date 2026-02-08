# Lifecycle Management

MicroAPI provides multiple ways to run code during application startup and shutdown: individual hooks, and lifespan context managers.

## Startup and Shutdown Hooks

Register functions that run when the server starts or stops:

```python
from microapi import MicroAPI

app = MicroAPI()

@app.on_startup
async def startup():
    print("Server starting...")
    await initialize_database()
    await warm_up_cache()

@app.on_shutdown
async def shutdown():
    print("Server stopping...")
    await close_database()
    await flush_metrics()
```

### Multiple Hooks

You can register multiple hooks — they execute in registration order:

```python
@app.on_startup
async def init_db():
    app.db = await create_pool()

@app.on_startup
async def init_cache():
    app.cache = await connect_redis()

@app.on_shutdown
async def cleanup_db():
    await app.db.close()

@app.on_shutdown
async def cleanup_cache():
    await app.cache.close()
```

### Sync Hooks

Both sync and async functions are supported:

```python
@app.on_startup
def setup_logging():
    logging.basicConfig(level=logging.INFO)
```

### Constructor Registration

```python
app = MicroAPI(
    on_startup=[init_db, init_cache],
    on_shutdown=[cleanup_db, cleanup_cache],
)
```

## Lifespan Context Manager

For more control, use a lifespan context manager. This is the recommended approach for managing resources that need both setup and teardown:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # Startup
    db = await create_database_pool()
    cache = await connect_redis()
    print("Resources initialized")

    yield  # Server runs here

    # Shutdown
    await cache.close()
    await db.close()
    print("Resources cleaned up")

app = MicroAPI(lifespan=lifespan)
```

### Raw Async Generator

You can also pass a raw async generator function (without `@asynccontextmanager`):

```python
async def lifespan(app):
    # Startup
    db = await create_pool()
    yield
    # Shutdown
    await db.close()

app = MicroAPI(lifespan=lifespan)
```

MicroAPI automatically detects whether you've passed a raw async generator or a decorated context manager and handles both correctly.

### Combining Hooks and Lifespan

You can use both hooks and lifespan together. The execution order is:

1. `on_startup` hooks run first
2. Lifespan startup (before `yield`)
3. **Server runs**
4. Lifespan shutdown (after `yield`)
5. `on_shutdown` hooks run last

```python
@asynccontextmanager
async def lifespan(app):
    print("2. Lifespan startup")
    yield
    print("4. Lifespan shutdown")

app = MicroAPI(lifespan=lifespan)

@app.on_startup
async def hook_start():
    print("1. on_startup hook")

@app.on_shutdown
async def hook_stop():
    print("5. on_shutdown hook")
```

## Hot Reload

Enable hot reload to automatically restart the server when source files change:

```python
app.run(
    transport=HTTPTransport(port=8080),
    reload=True,
)
```

Or via CLI:

```bash
microapi run server.main:app --reload
```

Hot reload uses [watchfiles](https://watchfiles.helpmanual.io/) to monitor the current directory for `.py` file changes. When a change is detected, the server process is restarted.

### How It Works

1. MicroAPI spawns the server in a subprocess
2. `watchfiles` monitors the working directory for `.py` changes
3. On change, the subprocess is terminated and restarted
4. Signal handlers are properly cleaned up between restarts

### Limitations

- Only `.py` files in the current directory tree are watched
- Changes to dependencies outside the project won't trigger reload
- Not recommended for production — use a process manager instead

## Signal Handling

MicroAPI installs signal handlers for graceful shutdown:

- **SIGINT** (Ctrl+C) — triggers shutdown
- **SIGTERM** — triggers shutdown (used by Docker, systemd, etc.)

When a signal is received:
1. The shutdown event is set
2. The transport server is stopped gracefully
3. Lifespan shutdown runs
4. `on_shutdown` hooks execute
5. Signal handlers are removed (clean for hot reload)

## Production Deployment

For production, use a process manager instead of hot reload:

### With systemd

```ini
# /etc/systemd/system/my-service.service
[Unit]
Description=My MicroAPI Service
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/my-service
ExecStart=/opt/my-service/.venv/bin/python -m server.main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### With Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install microapi[http]
CMD ["python", "server/main.py"]
```

### With supervisord

```ini
[program:my-service]
command=/opt/my-service/.venv/bin/python -m server.main
directory=/opt/my-service
autostart=true
autorestart=true
stderr_logfile=/var/log/my-service.err.log
stdout_logfile=/var/log/my-service.out.log
```
