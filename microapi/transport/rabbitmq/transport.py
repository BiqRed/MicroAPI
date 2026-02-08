"""RabbitMQ transport — request/response over AMQP queues."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from microapi._logging import get_logger
from microapi.protocol import Envelope, MessageType, MethodType, Request, StatusCode
from microapi.serialization import deserialize, serialize, to_dict
from microapi.transport.base import Transport, TransportClient, TransportServer
from microapi.types import Stream

if TYPE_CHECKING:
    from microapi.routing import Router

logger = get_logger("transport.rabbitmq")

_DEFAULT_REQUEST_QUEUE = "microapi-requests"
_DEFAULT_RESPONSE_QUEUE = "microapi-responses"


class RabbitMQServer(TransportServer):
    """RabbitMQ transport server.

    Consumes requests from ``request_queue`` and publishes
    responses to the ``reply_to`` queue from the message properties
    (or ``response_queue`` as fallback).
    """

    def __init__(
        self,
        url: str = "amqp://guest:guest@localhost:5672/",
        request_queue: str = _DEFAULT_REQUEST_QUEUE,
        response_queue: str = _DEFAULT_RESPONSE_QUEUE,
        prefetch_count: int = 10,
    ) -> None:
        self.url = url
        self.request_queue = request_queue
        self.response_queue = response_queue
        self.prefetch_count = prefetch_count
        self._connection: Any = None
        self._channel: Any = None
        self._router: Router | None = None
        self._running = False

    async def start(self, router: Router) -> None:
        import aio_pika

        self._router = router
        self._connection = await aio_pika.connect_robust(self.url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch_count)

        # Declare queues
        await self._channel.declare_queue(self.request_queue, durable=True)
        await self._channel.declare_queue(self.response_queue, durable=True)

        self._running = True
        logger.info("RabbitMQ server started (url=%s, queue=%s)", self.url, self.request_queue)

    async def stop(self) -> None:
        self._running = False
        if self._connection:
            await self._connection.close()
        logger.info("RabbitMQ server stopped")

    async def serve_forever(self) -> None:
        import aio_pika

        assert self._channel is not None
        queue = await self._channel.get_queue(self.request_queue)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._running:
                    break
                async with message.process():
                    asyncio.ensure_future(self._handle_message(message))

    async def _handle_message(self, message: Any) -> None:
        import aio_pika

        assert self._router is not None
        assert self._channel is not None

        try:
            data = deserialize(message.body)
            envelope = Envelope.from_dict(data)
        except Exception:
            logger.warning("Invalid RabbitMQ message")
            return

        reply_to = self.response_queue
        if message.reply_to:
            reply_to = message.reply_to

        request = Request(
            service=envelope.service,
            method=envelope.method,
            payload=envelope.payload,
            metadata=envelope.metadata,
            id=envelope.id,
        )

        # Handle client streaming
        client_stream: Stream[Any] | None = None
        try:
            method_type = self._router.get_method_type(envelope.service, envelope.method)
        except Exception:
            method_type = MethodType.UNARY

        if method_type in (MethodType.CLIENT_STREAMING, MethodType.BIDI_STREAMING):
            client_stream = Stream()
            if isinstance(envelope.payload, list):
                method_info = self._router.get_method_info(envelope.service, envelope.method)
                for item in envelope.payload:
                    if method_info.stream_input_type and isinstance(item, dict):
                        obj = method_info.stream_input_type.model_validate(item)
                        await client_stream._feed(obj)
                    else:
                        await client_stream._feed(item)
            await client_stream._close()

        response = await self._router.handle_request(request, client_stream)

        exchange = self._channel.default_exchange

        if response.is_streaming and hasattr(response.payload, "__aiter__"):
            async for item in response.payload:
                push = Envelope(
                    type=MessageType.STREAM_PUSH,
                    id=envelope.id,
                    payload=to_dict(item) if hasattr(item, "model_dump") else item,
                )
                await exchange.publish(
                    aio_pika.Message(body=serialize(push.to_dict())),
                    routing_key=reply_to,
                )
            end = Envelope(type=MessageType.STREAM_END, id=envelope.id)
            await exchange.publish(
                aio_pika.Message(body=serialize(end.to_dict())),
                routing_key=reply_to,
            )
        else:
            resp = Envelope(
                type=MessageType.RESPONSE,
                id=envelope.id,
                payload=response.payload if isinstance(response.payload, dict) else None,
                error=response.error,
                status_code=response.status_code.value,
            )
            await exchange.publish(
                aio_pika.Message(
                    body=serialize(resp.to_dict()),
                    correlation_id=envelope.id,
                ),
                routing_key=reply_to,
            )


class RabbitMQClient(TransportClient):
    """RabbitMQ client — publishes requests, consumes responses."""

    def __init__(
        self,
        url: str = "amqp://guest:guest@localhost:5672/",
        request_queue: str = _DEFAULT_REQUEST_QUEUE,
        response_queue: str | None = None,
    ) -> None:
        self.url = url
        self.request_queue = request_queue
        self.response_queue = response_queue or f"microapi-response-{uuid.uuid4().hex[:8]}"
        self._connection: Any = None
        self._channel: Any = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._recv_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        import aio_pika

        self._connection = await aio_pika.connect_robust(self.url)
        self._channel = await self._connection.channel()
        await self._channel.declare_queue(self.response_queue, durable=False, auto_delete=True)
        self._recv_task = asyncio.create_task(self._receive_loop())
        logger.debug("RabbitMQ client connected to %s", self.url)

    async def close(self) -> None:
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._connection:
            await self._connection.close()

    async def request(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        import aio_pika

        assert self._channel is not None

        envelope = Envelope(
            type=MessageType.REQUEST,
            service=service,
            method=method,
            payload=payload,
            metadata=metadata or {},
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[envelope.id] = future

        exchange = self._channel.default_exchange
        await exchange.publish(
            aio_pika.Message(
                body=serialize(envelope.to_dict()),
                reply_to=self.response_queue,
                correlation_id=envelope.id,
            ),
            routing_key=self.request_queue,
        )

        return await asyncio.wait_for(future, timeout=30.0)

    async def _receive_loop(self) -> None:
        assert self._channel is not None
        try:
            queue = await self._channel.get_queue(self.response_queue)
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            data = deserialize(message.body)
                            envelope = Envelope.from_dict(data)
                        except Exception:
                            continue

                        if envelope.type == MessageType.RESPONSE:
                            fut = self._pending.pop(envelope.id, None)
                            if fut and not fut.done():
                                fut.set_result(envelope.payload or {})
        except asyncio.CancelledError:
            pass


class RabbitMQTransport(Transport):
    """RabbitMQ transport.

    Example::

        from microapi.transport.rabbitmq import RabbitMQTransport

        app.run(transport=RabbitMQTransport(url="amqp://localhost:5672"))
    """

    def __init__(
        self,
        url: str = "amqp://guest:guest@localhost:5672/",
        request_queue: str = _DEFAULT_REQUEST_QUEUE,
        response_queue: str = _DEFAULT_RESPONSE_QUEUE,
    ) -> None:
        self.url = url
        self.request_queue = request_queue
        self.response_queue = response_queue

    def create_server(self) -> TransportServer:
        return RabbitMQServer(
            url=self.url,
            request_queue=self.request_queue,
            response_queue=self.response_queue,
        )

    def create_client(self) -> TransportClient:
        return RabbitMQClient(
            url=self.url,
            request_queue=self.request_queue,
        )
