from pathlib import Path

from microapi.transport.base import Transport
from microapi.utils import AddressValidators


class gRPC(AddressValidators, Transport):
    def __init__(
            self,
            host: str = 'localhost',
            port: int = 50051,
            generate_protos: bool = False,
            protos_dir: Path | str = Path('protos')
    ) -> None:
        super().__init__('grpc')

        self.host = self._validate_host(host)
        self.port = self._validate_port(port)

        if isinstance(protos_dir, str):
            protos_dir = Path(protos_dir)

        self.generate_protos = generate_protos
        self.protos_dir = protos_dir

