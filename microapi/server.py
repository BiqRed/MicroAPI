from pathlib import Path
from typing import Sequence, Callable, Any

from microapi.generator import LibGenerator
from microapi.service import Service
from microapi.middleware import Middleware
from microapi.types import Lifespan
from microapi.transport import Transport, GRPC
from microapi.hot_reload import HotReload


class MicroAPI:
    def __init__(
            self,
            *,
            services: Sequence[Service] | None = None,
            version: int | None = None,
            middlewares: Sequence[Middleware] | None = None,
            on_startup: Sequence[Callable[[], Any]] | None = None,
            on_shutdown: Sequence[Callable[[], Any]] | None = None,
            lifespan: Lifespan | None = None
    ) -> None:
        self.services: dict[str, Service] = {}

        if services is not None:
            for service in services:
                self.add_service(service)

        self.version: int = version if version is not None else 1
        self.middlewares: list[Middleware] = list(middlewares) if middlewares is not None else []
        self.on_startup: Sequence[Callable[[], Any]] = on_startup or []
        self.on_shutdown: Sequence[Callable[[], Any]] = on_shutdown or []
        self.lifespan: Lifespan | None = lifespan

    def add_service(self, service: Service) -> None:
        if service.name in self.services:
            raise KeyError(f"Service '{service.name}' already exists")
        self.services[service.name] = service

    def add_middleware(self, middleware: Middleware) -> None:
        self.middlewares.append(middleware)

    async def _run_server(self, transport: Transport) -> None:
        pass

    async def run(
            self,
            transport: Transport = GRPC(),
            *,
            auto_generate_lib: bool = True,
            generated_lib_dir: str = Path('lib'),
            refresh: bool = False
    ) -> None:

        if isinstance(generated_lib_dir, str):
            generated_lib_dir = Path(generated_lib_dir)

        lib_generator: LibGenerator | None = None
        if auto_generate_lib:
            lib_generator = LibGenerator(generated_lib_dir, transport)
            lib_generator.generate()

        if refresh:
            HotReload()

        await self._run_server(transport)
