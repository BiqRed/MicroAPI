from microapi import MicroAPI
from microapi.transport import gRPC

from examples.server import service as users_service
from examples.middlewares import AuthMiddleware

server = MicroAPI()

server.add_service(users_service)

server.add_middleware(AuthMiddleware())


if __name__ == '__main__':
    server.run(
        transport=gRPC(
            host='127.0.0.1',
            port=50050,
            generate_protos=True,
            protos_dir='protos',
        ),
        auto_generate_lib=True,
        generated_lib_dir='lib',
        refresh=True,
    )
