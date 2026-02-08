"""Example MicroAPI server with the users service."""

from middleware import AuthMiddleware, LoggingMiddleware
from service import service as users_service

from microapi import MicroAPI
from microapi.transport.http import HTTPTransport

# Create the application
app = MicroAPI()

# Register services
app.add_service(users_service)

# Add middleware (processed in order)
app.add_middleware(LoggingMiddleware())
app.add_middleware(AuthMiddleware())


if __name__ == "__main__":
    # Run with HTTP transport
    app.run(
        transport=HTTPTransport(host="127.0.0.1", port=8080),
        auto_generate_lib=True,
        generated_lib_dir="../shared/lib",
        reload=False,
        log_level="INFO",
    )

    # Alternative: run with gRPC
    # from microapi.transport.grpc import GRPCTransport
    # app.run(
    #     transport=GRPCTransport(host="127.0.0.1", port=50051),
    #     auto_generate_lib=True,
    #     generated_lib_dir="../shared/lib",
    #     generate_protos=True,
    #     protos_dir="protos",
    # )

    # Alternative: run with WebSocket
    # from microapi.transport.websocket import WebSocketTransport
    # app.run(
    #     transport=WebSocketTransport(host="127.0.0.1", port=8765),
    #     auto_generate_lib=True,
    #     generated_lib_dir="../shared/lib",
    # )
