from pathlib import Path

from .transport import TransportBase


class LibGenerator:
    def __init__(self, lib_dir: Path, transport: TransportBase):
        self.lib_dir: Path = lib_dir
        self.transport: TransportBase = transport

    def generate(self) -> None:
        pass
