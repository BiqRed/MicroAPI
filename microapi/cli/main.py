"""MicroAPI CLI — manage your microservices framework from the terminal."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="microapi",
    help="MicroAPI — Python microservices framework CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the MicroAPI version."""
    console.print(Panel("[bold cyan]MicroAPI[/bold cyan] v0.1.0", expand=False))


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@app.command()
def run(
    app_path: str = typer.Argument(
        ...,
        help="Import path to the MicroAPI app, e.g. 'server.main:app'",
    ),
    transport: str = typer.Option(
        "http",
        "--transport",
        "-t",
        help="Transport to use: grpc, http, websocket",
    ),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable hot reload"),
    generate_lib: bool = typer.Option(False, "--generate-lib", "-g", help="Auto-generate client library"),
    lib_dir: str = typer.Option("lib", "--lib-dir", help="Output directory for generated library"),
    generate_protos: bool = typer.Option(False, "--generate-protos", help="Generate .proto files"),
    protos_dir: str = typer.Option("protos", "--protos-dir", help="Output directory for .proto files"),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level"),
) -> None:
    """Run a MicroAPI server."""
    # Import the app
    microapi_app = _import_app(app_path)

    # Create transport
    transport_obj = _create_transport(transport, host, port)

    console.print("[bold green]Starting MicroAPI server[/bold green]")
    console.print(f"  Transport: [cyan]{transport}[/cyan] on {host}:{port}")
    if reload:
        console.print("  [yellow]Hot reload enabled[/yellow]")

    microapi_app.run(
        transport=transport_obj,
        auto_generate_lib=generate_lib,
        generated_lib_dir=lib_dir,
        generate_protos=generate_protos,
        protos_dir=protos_dir,
        reload=reload,
        log_level=log_level,
    )


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


@app.command()
def generate(
    app_path: str = typer.Argument(
        ...,
        help="Import path to the MicroAPI app, e.g. 'server.main:app'",
    ),
    output: str = typer.Option("lib", "--output", "-o", help="Output directory"),
    protos: bool = typer.Option(False, "--protos", help="Also generate .proto files"),
    protos_dir: str = typer.Option("protos", "--protos-dir", help="Output directory for .proto files"),
) -> None:
    """Generate client library (and optionally .proto files)."""
    microapi_app = _import_app(app_path)
    output_path = Path(output)

    from microapi.generator import generate_proto_files, generate_python_lib

    console.print("[bold]Generating client library...[/bold]")
    generate_python_lib(microapi_app.router.services, output_path)
    console.print(f"  [green]Client library generated in {output_path}[/green]")

    if protos:
        protos_path = Path(protos_dir)
        generate_proto_files(microapi_app.router.services, protos_path)
        console.print(f"  [green].proto files generated in {protos_path}[/green]")


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


@app.command()
def info(
    app_path: str = typer.Argument(
        ...,
        help="Import path to the MicroAPI app, e.g. 'server.main:app'",
    ),
) -> None:
    """Display information about a MicroAPI application."""
    microapi_app = _import_app(app_path)

    table = Table(title="MicroAPI Services", show_header=True, header_style="bold cyan")
    table.add_column("Service", style="green")
    table.add_column("Method", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Input", style="dim")
    table.add_column("Output", style="dim")

    for svc_name, service in microapi_app.router.services.items():
        for method_info in service.methods.values():
            input_name = method_info.input_type.__name__ if method_info.input_type else "-"
            output_name = (
                method_info.output_type.__name__
                if method_info.output_type and isinstance(method_info.output_type, type)
                else "-"
            )
            table.add_row(
                svc_name,
                method_info.generated_name,
                method_info.method_type.value,
                input_name,
                output_name,
            )

    console.print(table)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command()
def init(
    name: str = typer.Argument("myservice", help="Project name"),
    directory: str = typer.Option(".", "--dir", "-d", help="Target directory"),
) -> None:
    """Scaffold a new MicroAPI project."""
    base = Path(directory) / name
    base.mkdir(parents=True, exist_ok=True)

    # Create service file
    (base / "service.py").write_text(
        f'''"""Service definition for {name}."""

from microapi import Service, Schema, types


class Payload(Schema):
    message: str


class Result(Schema):
    reply: str


service = Service("{name}")


@service.method
async def echo(payload: Payload) -> Result:
    return Result(reply=f"Echo: {{payload.message}}")
''',
        encoding="utf-8",
    )

    # Create main file
    (base / "main.py").write_text(
        f'''"""MicroAPI server for {name}."""

from microapi import MicroAPI
from microapi.transport.http import HTTPTransport

from service import service

app = MicroAPI()
app.add_service(service)

if __name__ == "__main__":
    app.run(transport=HTTPTransport(port=8080), reload=True)
''',
        encoding="utf-8",
    )

    console.print(f"[bold green]Created MicroAPI project at {base}[/bold green]")
    console.print(f"  Run with: [cyan]microapi run {name}.main:app[/cyan]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_app(app_path: str) -> Any:
    """Import a MicroAPI app from a dotted path like 'module.sub:app'."""
    from microapi.app import MicroAPI

    # Add cwd to sys.path
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    if ":" in app_path:
        module_path, attr_name = app_path.rsplit(":", 1)
    else:
        module_path = app_path
        attr_name = "app"

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        console.print(f"[red]Error: Could not import '{module_path}': {e}[/red]")
        raise typer.Exit(1) from e

    app_obj = getattr(module, attr_name, None)
    if app_obj is None:
        console.print(f"[red]Error: '{attr_name}' not found in '{module_path}'[/red]")
        raise typer.Exit(1)

    if not isinstance(app_obj, MicroAPI):
        console.print(f"[red]Error: '{attr_name}' is not a MicroAPI instance[/red]")
        raise typer.Exit(1)

    return app_obj


def _create_transport(transport_name: str, host: str, port: int) -> Any:
    """Create a transport instance from a name string."""

    transports = {
        "grpc": ("microapi.transport.grpc", "GRPCTransport"),
        "http": ("microapi.transport.http", "HTTPTransport"),
        "websocket": ("microapi.transport.websocket", "WebSocketTransport"),
        "ws": ("microapi.transport.websocket", "WebSocketTransport"),
    }

    if transport_name.lower() not in transports:
        console.print(f"[red]Unknown transport: {transport_name}[/red]")
        console.print(f"Available: {', '.join(transports.keys())}")
        raise typer.Exit(1)

    module_path, class_name = transports[transport_name.lower()]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(host=host, port=port)


if __name__ == "__main__":
    app()
