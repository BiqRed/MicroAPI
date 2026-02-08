# CLI Reference

MicroAPI includes a CLI tool powered by [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/). It provides commands for running servers, generating code, scaffolding projects, and inspecting services.

## Installation

The CLI is included with the core package:

```bash
pip install microapi
```

After installation, the `microapi` command is available:

```bash
microapi --help
```

## Commands

### `microapi run`

Start a MicroAPI server.

```bash
microapi run <app_path> [OPTIONS]
```

**Arguments:**
- `app_path` — Python import path to the MicroAPI app (e.g., `server.main:app`)

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--transport` | `str` | `http` | Transport backend: `http`, `grpc`, `ws` |
| `--host` | `str` | `0.0.0.0` | Bind host |
| `--port` | `int` | `8080` | Bind port |
| `--reload` | flag | `False` | Enable hot reload |
| `--generate-lib` | flag | `False` | Auto-generate client library |
| `--lib-dir` | `str` | `lib` | Output directory for generated lib |
| `--generate-protos` | flag | `False` | Generate .proto files |
| `--protos-dir` | `str` | `protos` | Output directory for .proto files |
| `--log-level` | `str` | `INFO` | Logging level |

**Examples:**

```bash
# Basic HTTP server
microapi run server.main:app

# gRPC server with proto generation
microapi run server.main:app --transport grpc --port 50051 --generate-protos

# Development with hot reload
microapi run server.main:app --reload --generate-lib --log-level DEBUG

# WebSocket server
microapi run server.main:app --transport ws --port 8765
```

### `microapi generate`

Generate client libraries and/or Protobuf files without starting the server.

```bash
microapi generate <app_path> [OPTIONS]
```

**Arguments:**
- `app_path` — Python import path to the MicroAPI app

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output` | `str` | `lib` | Output directory for Python client |
| `--protos` | flag | `False` | Also generate .proto files |
| `--protos-dir` | `str` | `protos` | Output directory for .proto files |

**Examples:**

```bash
# Generate Python client library
microapi generate server.main:app --output shared/lib

# Generate both Python client and proto files
microapi generate server.main:app --output lib --protos --protos-dir protos
```

### `microapi info`

Display information about a MicroAPI application: registered services, methods, schemas, and method types.

```bash
microapi info <app_path>
```

**Example output:**

```
╭─────────────────────────── MicroAPI Application ───────────────────────────╮
│                                                                            │
│  Services: 2                                                               │
│  Version:  1                                                               │
│                                                                            │
│  ── users ──                                                               │
│  Methods:                                                                  │
│    get_user     UNARY             GetUserPayload → User                    │
│    list_users   SERVER_STREAMING  ListPayload → Streaming[User]            │
│    add_users    CLIENT_STREAMING  Stream[User] → None                      │
│    chat         BIDI_STREAMING    Stream[Message] → Streaming[Response]    │
│                                                                            │
│  ── orders ──                                                              │
│  Methods:                                                                  │
│    create_order UNARY             OrderPayload → Order                     │
│                                                                            │
╰────────────────────────────────────────────────────────────────────────────╯
```

### `microapi init`

Scaffold a new MicroAPI project with a standard directory structure.

```bash
microapi init <project_name>
```

Creates:

```
my_service/
├── server/
│   ├── __init__.py
│   ├── main.py
│   ├── schemas.py
│   └── service.py
├── client/
│   └── main.py
├── pyproject.toml
└── README.md
```

### `microapi version`

Print the installed MicroAPI version.

```bash
microapi version
```

Output:
```
MicroAPI v1.1.0
```

## App Path Format

The `<app_path>` argument follows the `module.path:variable` format:

- `server.main:app` — imports `app` from `server/main.py`
- `myapp:application` — imports `application` from `myapp.py`
- `package.module:create_app()` — calls `create_app()` to get the app

The module must be importable from the current directory.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MICROAPI_LOG_LEVEL` | Override default log level |
| `MICROAPI_HOST` | Override default host |
| `MICROAPI_PORT` | Override default port |
