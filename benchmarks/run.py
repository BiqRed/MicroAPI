"""Run local, reproducible benchmarks.

Benchmarks included:
- FastAPI over HTTP (uvicorn + httpx)
- MicroAPI over HTTP (aiohttp transport)
- MicroAPI over gRPC (custom h2 transport)
- (Optional) Raw aiohttp baseline

This is NOT a scientific benchmark harness. It is designed to be:
- easy to run locally
- stable on CI-disabled environments
- clear enough to paste results into README

Usage:
  uv sync --extra bench --extra http --extra grpc
  uv run python -m benchmarks.run
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import platform
import socket
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel as _PydanticBaseModel

from microapi import Schema as _MicroSchema


def _pick_free_port(host: str = "127.0.0.1") -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind((host, 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(s.getsockname()[1])


async def _wait_port(host: str, port: int, *, timeout_s: float = 5.0) -> None:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError:
            await asyncio.sleep(0.02)
            continue
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return
    raise TimeoutError(f"Port did not open: {host}:{port}")


def _pct(values: list[float], percentile: float) -> float:
    """Nearest-rank percentile on a sorted list of float values."""
    if not values:
        return 0.0
    if percentile <= 0:
        return values[0]
    if percentile >= 100:
        return values[-1]
    k = int(round((percentile / 100.0) * (len(values) - 1)))
    return values[k]


@dataclass(frozen=True)
class BenchResult:
    name: str
    n: int
    total_s: float
    rps: float
    p50_ms: float
    p95_ms: float


# NOTE: This module uses `from __future__ import annotations`.
# FastAPI and MicroAPI introspection commonly uses `typing.get_type_hints()`
# with function globals; if we define models inside benchmark functions,
# annotations become strings that cannot be resolved (leading FastAPI to treat
# them as query params, and MicroAPI to mis-detect schemas).
# Keep benchmark schemas/models at module scope so they resolve via globals.


class BenchPayload(_MicroSchema):
    x: int
    data: str


class BenchReply(_MicroSchema):
    x: int
    data: str


class FastAPIPayload(_PydanticBaseModel):
    x: int
    data: str


class FastAPIReply(_PydanticBaseModel):
    x: int
    data: str


def _render_bars_svg(
    *,
    results: list[BenchResult],
    title: str,
    subtitle: str,
    width: int = 980,
    height: int = 360,
) -> str:
    """Render a nice-looking bar chart as SVG (no extra deps)."""

    # Theme
    bg = "#0b1020"
    card = "#0f172a"
    border = "#223152"
    text = "#e5e7eb"
    muted = "#9aa4b2"
    grid = "#1f2a44"

    colors: dict[str, str] = {
        "FastAPI HTTP (uvicorn + httpx)": "#3b82f6",
        "MicroAPI HTTP (aiohttp)": "#22c55e",
        "MicroAPI gRPC (h2, JSON)": "#a855f7",
        "aiohttp raw HTTP (baseline)": "#94a3b8",
    }

    max_rps = max((r.rps for r in results), default=1.0)
    base_rps = results[0].rps if results else 0.0

    pad = 18
    header_h = 74
    row_h = 56
    left = 260
    right = 140
    top = header_h + 10
    bar_w = width - pad * 2 - left - right

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    rows = results
    chart_h = len(rows) * row_h
    total_h = max(height, pad * 2 + header_h + chart_h + 14)

    # Grid lines (vertical)
    grid_lines = []
    for i in range(1, 5):
        x = pad + left + int((bar_w * i) / 5)
        grid_lines.append(
            f'<line x1="{x}" y1="{top}" x2="{x}" y2="{top + chart_h}" '
            f'stroke="{grid}" stroke-width="1" />'
        )

    # Rows
    svg_rows: list[str] = []
    for idx, r in enumerate(rows):
        y = top + idx * row_h
        label_y = y + 20
        bar_y = y + 28

        value = r.rps
        rel = (value / base_rps) if base_rps > 0 else 0.0
        rel_txt = f"{rel:.2f}x" if idx != 0 and base_rps > 0 else "baseline"

        fill = colors.get(r.name, "#60a5fa")
        w = int((value / max_rps) * bar_w) if max_rps > 0 else 0
        x0 = pad + left

        # background track
        svg_rows.append(
            f'<rect x="{x0}" y="{bar_y}" width="{bar_w}" height="16" rx="8" '
            f'fill="#0b1226" stroke="{border}" stroke-width="1" />'
        )
        # bar
        title_txt = (
            f"{esc(r.name)}: {r.rps:,.0f} req/s, p50 {r.p50_ms:.3f} ms, p95 {r.p95_ms:.3f} ms"
        )
        svg_rows.append(
            f'<rect x="{x0}" y="{bar_y}" width="{w}" height="16" rx="8" fill="{fill}">'
            f"<title>{title_txt}</title></rect>"
        )

        # left labels
        svg_rows.append(
            f'<text x="{pad + 10}" y="{label_y}" fill="{text}" font-size="14" font-weight="600">'
            f"{esc(r.name)}</text>"
        )
        svg_rows.append(
            f'<text x="{pad + 10}" y="{label_y + 18}" fill="{muted}" font-size="12">'
            f"{r.p50_ms:.3f} ms p50 · {r.p95_ms:.3f} ms p95</text>"
        )

        # right values
        right_x = width - pad - right + 6
        svg_rows.append(
            f'<text x="{right_x}" y="{label_y}" fill="{text}" font-size="14" font-weight="700">'
            f"{r.rps:,.0f}</text>"
        )
        svg_rows.append(
            f'<text x="{right_x}" y="{label_y + 18}" fill="{muted}" font-size="12">'
            f"{esc(rel_txt)}</text>"
        )

    lines: list[str] = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_h}" '
        f'viewBox="0 0 {width} {total_h}" role="img">'
    )
    lines.append("  <defs>")
    lines.append('    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">')
    lines.append(f'      <stop offset="0%" stop-color="{bg}"/>')
    lines.append('      <stop offset="100%" stop-color="#070b16"/>')
    lines.append("    </linearGradient>")
    lines.append("  </defs>")
    lines.append(f'  <rect x="0" y="0" width="{width}" height="{total_h}" fill="url(#bg)"/>')
    lines.append(
        f'  <rect x="{pad}" y="{pad}" width="{width - pad * 2}" height="{total_h - pad * 2}" '
        f'rx="16" fill="{card}" stroke="{border}" stroke-width="1"/>'
    )
    lines.append(
        f'  <text x="{pad + 18}" y="{pad + 30}" fill="{text}" font-size="20" font-weight="800">'
        f"{esc(title)}</text>"
    )
    lines.append(
        f'  <text x="{pad + 18}" y="{pad + 52}" fill="{muted}" font-size="12">{esc(subtitle)}</text>'
    )
    lines.append(
        f'  <text x="{pad + left}" y="{top - 10}" fill="{muted}" font-size="12">Throughput (req/s)</text>'
    )
    lines.append(f"  {''.join(grid_lines)}")
    lines.append(f"  {''.join(svg_rows)}")
    lines.append(
        f'  <text x="{pad + 18}" y="{total_h - pad - 10}" fill="{muted}" font-size="11">'
        "Higher is better. Hover bars for details. Generated by benchmarks/run.py</text>"
    )
    lines.append("</svg>")
    return "\n".join(lines)


async def _time_requests(n: int, call: Callable[[], Awaitable[None]]) -> tuple[float, list[float]]:
    lat_ms: list[float] = []
    start = time.perf_counter()
    for _ in range(n):
        t0 = time.perf_counter()
        await call()
        lat_ms.append((time.perf_counter() - t0) * 1000.0)
    total = time.perf_counter() - start
    return total, lat_ms


async def bench_microapi_http(*, host: str, port: int, warmup: int, n: int, payload: dict[str, Any]) -> BenchResult:
    from microapi import MicroAPI, Service
    from microapi.transport.http import HTTPTransport

    svc = Service("bench")

    @svc.method
    async def echo(p: BenchPayload) -> BenchReply:
        return BenchReply(x=p.x, data=p.data)

    app = MicroAPI(services=[svc])
    transport = HTTPTransport(host=host, port=port)
    server = transport.create_server()
    await server.start(app.router)

    client = transport.create_client()
    await client.connect()

    async def call() -> None:
        await client.request("bench", "echo", payload)

    # warmup
    for _ in range(warmup):
        await call()

    total_s, lat_ms = await _time_requests(n, call)

    await client.close()
    await server.stop()

    lat_ms.sort()
    return BenchResult(
        name="MicroAPI HTTP (aiohttp)",
        n=n,
        total_s=total_s,
        rps=n / total_s if total_s > 0 else 0.0,
        p50_ms=_pct(lat_ms, 50),
        p95_ms=_pct(lat_ms, 95),
    )


async def bench_microapi_grpc(*, host: str, port: int, warmup: int, n: int, payload: dict[str, Any]) -> BenchResult:
    from microapi import MicroAPI, Service
    from microapi.transport.grpc import GRPCTransport

    svc = Service("bench")

    @svc.method
    async def echo(p: BenchPayload) -> BenchReply:
        return BenchReply(x=p.x, data=p.data)

    app = MicroAPI(services=[svc])
    transport = GRPCTransport(host=host, port=port)
    server = transport.create_server()
    await server.start(app.router)

    client = transport.create_client()
    await client.connect()
    await asyncio.sleep(0.05)  # let h2 settle

    async def call() -> None:
        await client.request("bench", "echo", payload)

    for _ in range(warmup):
        await call()

    total_s, lat_ms = await _time_requests(n, call)

    await client.close()
    await server.stop()

    lat_ms.sort()
    return BenchResult(
        name="MicroAPI gRPC (h2, JSON)",
        n=n,
        total_s=total_s,
        rps=n / total_s if total_s > 0 else 0.0,
        p50_ms=_pct(lat_ms, 50),
        p95_ms=_pct(lat_ms, 95),
    )


async def bench_fastapi_http(*, host: str, port: int, warmup: int, n: int, payload: dict[str, Any]) -> BenchResult:
    # Imports are inside to keep base installs light.
    import httpx
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import ORJSONResponse

    app = FastAPI(default_response_class=ORJSONResponse)

    @app.post("/echo", response_model=FastAPIReply)
    async def echo(p: FastAPIPayload) -> FastAPIReply:
        return FastAPIReply(x=p.x, data=p.data)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        loop="asyncio",
        http="h11",
    )
    server = uvicorn.Server(config)

    server_task = asyncio.create_task(server.serve())
    try:
        await _wait_port(host, port, timeout_s=5.0)

        async with httpx.AsyncClient(base_url=f"http://{host}:{port}", timeout=10.0) as client:

            async def call() -> None:
                r = await client.post("/echo", json=payload)
                if r.status_code != 200:
                    # FastAPI returns validation error details in JSON.
                    raise RuntimeError(f"FastAPI benchmark request failed: {r.status_code} {r.text}")

            for _ in range(warmup):
                await call()

            total_s, lat_ms = await _time_requests(n, call)

    finally:
        server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(server_task, timeout=5.0)

    lat_ms.sort()
    return BenchResult(
        name="FastAPI HTTP (uvicorn + httpx)",
        n=n,
        total_s=total_s,
        rps=n / total_s if total_s > 0 else 0.0,
        p50_ms=_pct(lat_ms, 50),
        p95_ms=_pct(lat_ms, 95),
    )


async def bench_raw_aiohttp(*, host: str, port: int, warmup: int, n: int, payload: dict[str, Any]) -> BenchResult:
    import aiohttp
    from aiohttp import web

    async def handler(request: web.Request) -> web.Response:
        data = await request.json()
        return web.json_response({"x": int(data["x"]), "data": str(data["data"])})

    app = web.Application()
    app.router.add_post("/echo", handler)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    async with aiohttp.ClientSession() as session:

        async def call() -> None:
            async with session.post(f"http://{host}:{port}/echo", json=payload) as resp:
                resp.raise_for_status()
                await resp.read()

        for _ in range(warmup):
            await call()

        total_s, lat_ms = await _time_requests(n, call)

    await runner.cleanup()

    lat_ms.sort()
    return BenchResult(
        name="aiohttp raw HTTP (baseline)",
        n=n,
        total_s=total_s,
        rps=n / total_s if total_s > 0 else 0.0,
        p50_ms=_pct(lat_ms, 50),
        p95_ms=_pct(lat_ms, 95),
    )


def _format_results_md(results: list[BenchResult]) -> str:
    lines = []
    lines.append("| Benchmark | Requests | Total (s) | Req/s | p50 (ms) | p95 (ms) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in results:
        lines.append(
            f"| {r.name} | {r.n:,} | {r.total_s:.3f} | {r.rps:,.0f} | {r.p50_ms:.3f} | {r.p95_ms:.3f} |"
        )
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--warmup", type=int, default=300)
    parser.add_argument("--requests", type=int, default=3000)
    parser.add_argument("--payload-bytes", type=int, default=64)
    parser.add_argument("--skip-aiohttp-baseline", action="store_true")
    parser.add_argument("--json-out", type=str, default="")
    parser.add_argument("--svg-out", type=str, default="")
    args = parser.parse_args()

    payload = {"x": 123, "data": "x" * int(args.payload_bytes)}

    host = str(args.host)
    warmup = int(args.warmup)
    n = int(args.requests)

    # Use different free ports to avoid cross-server interference.
    port_fastapi = _pick_free_port(host)
    port_micro_http = _pick_free_port(host)
    port_micro_grpc = _pick_free_port(host)
    port_aiohttp = _pick_free_port(host)

    results: list[BenchResult] = []

    # Order: baseline (FastAPI), MicroAPI HTTP, MicroAPI gRPC, raw aiohttp (optional)
    results.append(await bench_fastapi_http(host=host, port=port_fastapi, warmup=warmup, n=n, payload=payload))
    results.append(await bench_microapi_http(host=host, port=port_micro_http, warmup=warmup, n=n, payload=payload))
    results.append(await bench_microapi_grpc(host=host, port=port_micro_grpc, warmup=warmup, n=n, payload=payload))
    if not args.skip_aiohttp_baseline:
        results.append(await bench_raw_aiohttp(host=host, port=port_aiohttp, warmup=warmup, n=n, payload=payload))

    print()
    print("## Benchmark results (copy-paste into README)")
    print()
    print(_format_results_md(results))
    print()

    # Small extra: relative speed vs FastAPI baseline
    base = results[0].rps
    if base > 0:
        print("### Relative throughput vs FastAPI")
        for r in results[1:]:
            print(f"- {r.name}: {r.rps / base:.2f}x")

    meta = {
        "host": host,
        "warmup": warmup,
        "requests": n,
        "payload_bytes": int(args.payload_bytes),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data = {
        "meta": meta,
        "results": [
            {
                "name": r.name,
                "n": r.n,
                "total_s": r.total_s,
                "rps": r.rps,
                "p50_ms": r.p50_ms,
                "p95_ms": r.p95_ms,
            }
            for r in results
        ],
    }

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    if args.svg_out:
        out = Path(args.svg_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        title = "FastAPI vs MicroAPI (localhost) — Throughput"
        subtitle = (
            f"{meta['platform']} · Python {meta['python']} · payload≈{meta['payload_bytes']}B · "
            f"warmup={meta['warmup']} · n={meta['requests']}"
        )
        out.write_text(_render_bars_svg(results=results, title=title, subtitle=subtitle), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())

