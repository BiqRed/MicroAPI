"""MicroAPI application — the central entry point."""

from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Sequence

from microapi._logging import configure_logging, logger
from microapi.lifecycle import Lifespan, default_lifespan
from microapi.middleware import Middleware
from microapi.routing import Router
from microapi.service import Service
from microapi.transport.base import Transport, TransportServer


class MicroAPI:
    """The main MicroAPI application.

    Example::

        from microapi import MicroAPI, Service
        from microapi.transport.grpc import GRPCTransport

        app = MicroAPI()
        app.add_service(users_service)
        app.run(transport=GRPCTransport(port=50051))
    """

    def __init__(
        self,
        *,
        services: Sequence[Service] | None = None,
        middlewares: Sequence[Middleware] | None = None,
        on_startup: Sequence[Callable[[], Any]] | None = None,
        on_shutdown: Sequence[Callable[[], Any]] | None = None,
        lifespan: Lifespan | None = None,
        version: int = 1,
    ) -> None:
        self.version = version
        self._router = Router()
        self._on_startup: list[Callable[[], Any]] = list(on_startup or [])
        self._on_shutdown: list[Callable[[], Any]] = list(on_shutdown or [])
        self._lifespan = lifespan
        self._server: TransportServer | None = None
        self._shutdown_event: asyncio.Event | None = None

        if services:
            for svc in services:
                self.add_service(svc)
        if middlewares:
            for mw in middlewares:
                self.add_middleware(mw)

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def add_service(self, service: Service) -> None:
        """Register a :class:`Service` with the application."""
        self._router.register_service(service)

    def add_middleware(self, middleware: Middleware) -> None:
        """Append a :class:`Middleware` to the processing chain."""
        self._router.add_middleware(middleware)

    def on_startup(self, func: Callable[[], Any]) -> Callable[[], Any]:
        """Decorator to register a startup hook."""
        self._on_startup.append(func)
        return func

    def on_shutdown(self, func: Callable[[], Any]) -> Callable[[], Any]:
        """Decorator to register a shutdown hook."""
        self._on_shutdown.append(func)
        return func

    @property
    def router(self) -> Router:
        return self._router

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def run(
        self,
        transport: Transport,
        *,
        auto_generate_lib: bool = False,
        generated_lib_dir: str | Path = "lib",
        generate_protos: bool = False,
        protos_dir: str | Path = "protos",
        reload: bool = False,
        log_level: str = "INFO",
    ) -> None:
        """Start the application (blocking).

        Parameters
        ----------
        transport:
            Transport factory providing server/client creation.
        auto_generate_lib:
            If ``True``, auto-generate the client library before starting.
        generated_lib_dir:
            Directory for the generated client library.
        generate_protos:
            If ``True``, generate ``.proto`` files.
        protos_dir:
            Directory for generated ``.proto`` files.
        reload:
            If ``True``, enable hot-reload on source changes.
        log_level:
            Logging level (``DEBUG``, ``INFO``, ``WARNING``, etc.).
        """
        configure_logging(log_level)

        if reload:
            self._run_with_reload(transport, auto_generate_lib, generated_lib_dir, generate_protos, protos_dir)
        else:
            asyncio.run(
                self._serve(transport, auto_generate_lib, generated_lib_dir, generate_protos, protos_dir)
            )

    async def _serve(
        self,
        transport: Transport,
        auto_generate_lib: bool,
        generated_lib_dir: str | Path,
        generate_protos: bool,
        protos_dir: str | Path,
    ) -> None:
        """Async core of the server lifecycle."""
        self._shutdown_event = asyncio.Event()

        # Install signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)

        # Code generation
        if auto_generate_lib:
            self._generate_lib(generated_lib_dir)

        if generate_protos:
            self._generate_protos(protos_dir)

        # Lifespan
        lifespan_cm = self._lifespan or default_lifespan

        @asynccontextmanager
        async def _managed_lifespan() -> AsyncIterator[None]:
            # on_startup hooks
            for hook in self._on_startup:
                result = hook()
                if asyncio.iscoroutine(result):
                    await result
            try:
                async with asynccontextmanager(lifespan_cm)(self):
                    yield
            finally:
                # on_shutdown hooks
                for hook in self._on_shutdown:
                    result = hook()
                    if asyncio.iscoroutine(result):
                        await result

        async with _managed_lifespan():
            # Start transport server
            server = transport.create_server()
            self._server = server
            await server.start(self._router)

            logger.info("MicroAPI server started")

            # Wait for shutdown signal
            await self._shutdown_event.wait()

            logger.info("Shutting down...")
            await server.stop()

        logger.info("MicroAPI server stopped")

    def _run_with_reload(
        self,
        transport: Transport,
        auto_generate_lib: bool,
        generated_lib_dir: str | Path,
        generate_protos: bool,
        protos_dir: str | Path,
    ) -> None:
        """Launch with hot-reload via watchfiles."""
        from microapi.hot_reload import run_with_reload

        run_with_reload(
            self._serve,
            args=(transport, auto_generate_lib, generated_lib_dir, generate_protos, protos_dir),
        )

    def _generate_lib(self, output_dir: str | Path) -> None:
        """Generate Python client library."""
        from microapi.generator import generate_python_lib

        output_dir = Path(output_dir)
        generate_python_lib(self._router.services, output_dir)
        logger.info("Generated client library in %s", output_dir)

    def _generate_protos(self, output_dir: str | Path) -> None:
        """Generate .proto files."""
        from microapi.generator import generate_proto_files

        output_dir = Path(output_dir)
        generate_proto_files(self._router.services, output_dir)
        logger.info("Generated .proto files in %s", output_dir)
