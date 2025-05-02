from microapi.logging import logger
from microapi.service import Service


class MicroAPI:
    def __init__(self, services: list[Service] = None):
        self.services: dict[str, Service] = {}

        if services is not None:
            for service in services:
                self.add_service(service)

    def add_service(self, service: Service):
        if service.name in self.services:
            logger.warning(f"Service with name {service.name} already exists")
        self.services[service.name] = service

    async def run(self, *, refresh: bool = False):
        _ = self
        logger.info(f"MicroAPI server started with refresh={refresh}")
