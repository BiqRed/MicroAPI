## MicroAPI Benchmarks

These are **local, reproducible** benchmarks intended for README marketing and quick sanity checks.

They are **not** part of the normal unit/integration test suite because performance results are highly
dependent on:
- CPU / thermal throttling
- OS / kernel
- Python version
- background processes
- network stack details

### Requirements

Install benchmark dependencies + required transports:

```bash
uv sync --extra bench --extra http --extra grpc
```

### Run

```bash
uv run python -m benchmarks.run
```

You can tweak the run:

```bash
uv run python -m benchmarks.run --requests 10000 --warmup 500 --payload-bytes 256
```

### Generate an SVG chart (for README)

```bash
uv run python -m benchmarks.run --requests 5000 --warmup 500 --payload-bytes 128 \
  --json-out benchmarks/latest.json \
  --svg-out benchmarks/benchmark.svg
```

### What is measured

All benchmarks run on **localhost** and measure:
- **Req/s** (throughput)
- **p50 / p95 latency**

Compared setups:
- **FastAPI HTTP**: `uvicorn` server + `httpx` client
- **MicroAPI HTTP**: MicroAPI server + aiohttp transport + MicroAPI client
- **MicroAPI gRPC**: MicroAPI server + custom HTTP/2 h2 transport + MicroAPI client
- **aiohttp raw baseline** (optional): minimal aiohttp server/client without framework features

### Interpreting results

- FastAPI benchmark uses `ORJSONResponse` to avoid penalizing it with slow JSON serialization.
- MicroAPI uses `orjson` internally for protocol envelopes and Pydantic for schemas.
- MicroAPI gRPC and FastAPI HTTP are **different protocols**. The point is to show a realistic migration
  path: many teams build internal RPC over FastAPI/HTTP first, then switch to a dedicated RPC transport.

