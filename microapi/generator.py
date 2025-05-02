from pathlib import Path

from .transport import Transport


class LibGenerator:
    def __init__(self, lib_dir: Path, transport: Transport):
        self.lib_dir: Path = lib_dir
        self.transport: Transport = transport

    def generate(self) -> None:
        pass
