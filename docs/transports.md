# Transports

Transports handle the actual network communication between servers and clients. MicroAPI supports five transport backends, all with a consistent interface.

## Overview

| Transport | Protocol | Library | Install Extra | Default Port |
|-----------|----------|---------|---------------|-------------|
| HTTP | HTTP/1.1 | aiohttp | `http` | 8080 |
| gRPC | HTTP/2 | h2 | `grpc` | 50051 |
| WebSocket | WS | websockets | `ws` | 8765 |
| Kafka | TCP | aiokafka | `kafka` | 9092 |
| RabbitMQ | AMQP | aio-pika | `rabbitmq` | 5672 |

## HTTP Transport

Standard HTTP/1.1 transport using [aiohttp](https://docs.aiohttp.org/). Each RPC method maps to `POST /{service}/{method}`.

### Installation

```bash
pip install microapi[http]
```

### Server

```python
from microapi.transport.http import HTTPTransport

app.run(
    transport=HTTPTransport(
        host="0.0.0.0",    # Bind address
        port=8080,          # Listen port
    ),
)
```

### Client

```python
from microapi.transport.http import HTTPTransport
from microapi.client.base import Connection

transport = HTTPTransport(host="127.0.0.1", port=8080)
conn = Connection(transport.create_client())

async with conn:
    result = await users.get_user(user_id=1)
```

### How It Works

- **Unary**: `POST /{service}/{method}` with JSON body, JSON response
- **Server streaming**: `POST /{service}/{method}` returns NDJSON (newline-delimited JSON)
- **Client streaming**: `POST /{service}/{method}` with JSON array body
- **Health check**: `GET /health` returns `{"status": "ok"}`

### When to Use

- Simple setups, REST-like APIs
- When you need broad compatibility (any HTTP client can call it)
- Development and testing

---

## gRPC Transport

Custom HTTP/2 gRPC implementation built on [h2](https://python-hyper.org/projects/h2/). No `grpcio` dependency.

### Installation

```bash
pip install microapi[grpc]
```

### Server

```python
from microapi.transport.grpc import GRPCTransport

app.run(
    transport=GRPCTransport(
        host="0.0.0.0",
        port=50051,
    ),
)
```

### With SSL/TLS

```python
import ssl

ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_ctx.load_cert_chain("server.crt", "server.key")

app.run(
    transport=GRPCTransport(
        host="0.0.0.0",
        port=50051,
        ssl_context=ssl_ctx,
    ),
)
```

### Client

```python
from microapi.transport.grpc import GRPCTransport
from microapi.client.base import Connection

transport = GRPCTransport(host="127.0.0.1", port=50051)
conn = Connection(transport.create_client())

async with conn:
    result = await users.get_user(user_id=1)
```

### How It Works

- Uses HTTP/2 with proper flow control via the `h2` library
- gRPC wire format: length-prefixed frames with `application/grpc+json` content type
- Supports unary and server-streaming patterns natively
- Full `.proto` file generation for cross-language interop

### Protobuf Generation

```python
app.run(
    transport=GRPCTransport(port=50051),
    generate_protos=True,
    protos_dir="protos",
)
```

This generates standard `.proto` files that can be used with any gRPC implementation in any language:

```protobuf
syntax = "proto3";
package users;

message User {
    optional string username = 1;
    optional int64 age = 2;
}

service UsersService {
    rpc get_user(GetUserPayload) returns (User);
    rpc list_users(ListPayload) returns (stream User);
}
```

### When to Use

- Internal microservice communication
- When you need HTTP/2 performance
- Cross-language interop (via `.proto` files)

---

## WebSocket Transport

Persistent WebSocket connection with multiplexed request/response using [websockets](https://websockets.readthedocs.io/).

### Installation

```bash
pip install microapi[ws]
```

### Server

```python
from microapi.transport.websocket import WebSocketTransport

app.run(
    transport=WebSocketTransport(
        host="0.0.0.0",
        port=8765,
    ),
)
```

### Client

```python
from microapi.transport.websocket import WebSocketTransport
from microapi.client.base import Connection

transport = WebSocketTransport(host="127.0.0.1", port=8765)
conn = Connection(transport.create_client())

async with conn:
    result = await users.get_user(user_id=1)
```

### How It Works

- Single persistent WebSocket connection
- Messages are multiplexed using a unique `id` field per request
- Multiple concurrent requests over one connection
- Full streaming support (server, client, bidirectional)

### When to Use

- Real-time applications
- When you need persistent connections
- Low-latency scenarios
- Browser-to-service communication

---

## Kafka Transport

Event-driven transport using [Apache Kafka](https://kafka.apache.org/) via [aiokafka](https://aiokafka.readthedocs.io/).

### Installation

```bash
pip install microapi[kafka]
```

### Prerequisites

You need a running Kafka cluster. The simplest setup for development:

```bash
docker run -d --name kafka \
    -p 9092:9092 \
    -e KAFKA_CFG_NODE_ID=0 \
    -e KAFKA_CFG_PROCESS_ROLES=controller,broker \
    -e KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
    -e KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
    -e KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=0@localhost:9093 \
    -e KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER \
    bitnami/kafka:latest
```

### Server

```python
from microapi.transport.kafka import KafkaTransport

app.run(
    transport=KafkaTransport(
        bootstrap_servers="localhost:9092",
        request_topic="my-service-requests",
        response_topic="my-service-responses",
        group_id="my-service-group",
    ),
)
```

### Client

```python
from microapi.transport.kafka import KafkaTransport
from microapi.client.base import Connection

transport = KafkaTransport(
    bootstrap_servers="localhost:9092",
    request_topic="my-service-requests",
    response_topic="my-service-responses",
)
conn = Connection(transport.create_client())

async with conn:
    result = await users.get_user(user_id=1)
```

### When to Use

- Event-driven architectures
- High-throughput message processing
- When you need message durability and replay
- Fan-out to multiple consumers

---

## RabbitMQ Transport

Queue-based transport using [RabbitMQ](https://www.rabbitmq.com/) via [aio-pika](https://aio-pika.readthedocs.io/).

### Installation

```bash
pip install microapi[rabbitmq]
```

### Prerequisites

You need a running RabbitMQ instance:

```bash
docker run -d --name rabbitmq \
    -p 5672:5672 \
    -p 15672:15672 \
    rabbitmq:management
```

### Server

```python
from microapi.transport.rabbitmq import RabbitMQTransport

app.run(
    transport=RabbitMQTransport(
        url="amqp://guest:guest@localhost:5672/",
        request_queue="my-service-requests",
        response_queue="my-service-responses",
    ),
)
```

### Client

```python
from microapi.transport.rabbitmq import RabbitMQTransport
from microapi.client.base import Connection

transport = RabbitMQTransport(
    url="amqp://guest:guest@localhost:5672/",
    request_queue="my-service-requests",
    response_queue="my-service-responses",
)
conn = Connection(transport.create_client())

async with conn:
    result = await users.get_user(user_id=1)
```

### When to Use

- Task queues and work distribution
- When you need reliable message delivery with acknowledgments
- When you need routing patterns (direct, topic, fanout)

---

## Choosing a Transport

```
                    ┌──────────────┐
                    │ Need cross-  │
                    │ language?    │──── Yes ──→ gRPC
                    └──────┬───────┘
                           │ No
                    ┌──────┴───────┐
                    │ Need message │
                    │ queuing?     │──── Yes ──→ Kafka / RabbitMQ
                    └──────┬───────┘
                           │ No
                    ┌──────┴───────┐
                    │ Need real-   │
                    │ time/bidi?   │──── Yes ──→ WebSocket
                    └──────┬───────┘
                           │ No
                           ▼
                         HTTP
```
