"""Kafka transport — request/response over Kafka topics."""

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

logger = get_logger("transport.kafka")

_DEFAULT_REQUEST_TOPIC = "microapi-requests"
_DEFAULT_RESPONSE_TOPIC = "microapi-responses"


class KafkaServer(TransportServer):
    """Kafka transport server — consumes requests, produces responses.

    Request messages are consumed from ``request_topic``.
    Response messages are produced to the topic specified in the
    request's ``reply_topic`` metadata field (or ``response_topic``).
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        request_topic: str = _DEFAULT_REQUEST_TOPIC,
        response_topic: str = _DEFAULT_RESPONSE_TOPIC,
        group_id: str = "microapi-server",
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.request_topic = request_topic
        self.response_topic = response_topic
        self.group_id = group_id
        self._consumer: Any = None
        self._producer: Any = None
        self._router: Router | None = None
        self._running = False

    async def start(self, router: Router) -> None:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

        self._router = router
        self._consumer = AIOKafkaConsumer(
            self.request_topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda v: deserialize(v),
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: serialize(v),
        )
        await self._consumer.start()
        await self._producer.start()
        self._running = True
        logger.info(
            "Kafka server started (bootstrap=%s, topic=%s)",
            self.bootstrap_servers,
            self.request_topic,
        )

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        logger.info("Kafka server stopped")

    async def serve_forever(self) -> None:
        assert self._router is not None
        assert self._consumer is not None

        async for message in self._consumer:
            if not self._running:
                break
            asyncio.ensure_future(self._handle_message(message.value))

    async def _handle_message(self, data: dict[str, Any]) -> None:
        assert self._router is not None
        assert self._producer is not None

        try:
            envelope = Envelope.from_dict(data)
        except Exception:
            logger.warning("Invalid Kafka message: %s", data)
            return

        reply_topic = envelope.metadata.get("reply_topic", self.response_topic)

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

        # Send response(s)
        if response.is_streaming and hasattr(response.payload, "__aiter__"):
            async for item in response.payload:
                push = Envelope(
                    type=MessageType.STREAM_PUSH,
                    id=envelope.id,
                    payload=to_dict(item) if hasattr(item, "model_dump") else item,
                )
                await self._producer.send(reply_topic, push.to_dict())

            end = Envelope(type=MessageType.STREAM_END, id=envelope.id)
            await self._producer.send(reply_topic, end.to_dict())
        else:
            resp = Envelope(
                type=MessageType.RESPONSE,
                id=envelope.id,
                payload=response.payload if isinstance(response.payload, dict) else None,
                error=response.error,
                status_code=response.status_code.value,
            )
            await self._producer.send(reply_topic, resp.to_dict())


class KafkaClient(TransportClient):
    """Kafka client — produces requests, consumes responses."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        request_topic: str = _DEFAULT_REQUEST_TOPIC,
        response_topic: str = _DEFAULT_RESPONSE_TOPIC,
        group_id: str | None = None,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.request_topic = request_topic
        self.response_topic = response_topic
        self.group_id = group_id or f"microapi-client-{uuid.uuid4().hex[:8]}"
        self._producer: Any = None
        self._consumer: Any = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._recv_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: serialize(v),
        )
        self._consumer = AIOKafkaConsumer(
            self.response_topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda v: deserialize(v),
        )
        await self._producer.start()
        await self._consumer.start()
        self._recv_task = asyncio.create_task(self._receive_loop())
        logger.debug("Kafka client connected to %s", self.bootstrap_servers)

    async def close(self) -> None:
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._producer:
            await self._producer.stop()
        if self._consumer:
            await self._consumer.stop()

    async def request(
        self,
        service: str,
        method: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        assert self._producer is not None

        envelope = Envelope(
            type=MessageType.REQUEST,
            service=service,
            method=method,
            payload=payload,
            metadata={**(metadata or {}), "reply_topic": self.response_topic},
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[envelope.id] = future

        await self._producer.send(self.request_topic, envelope.to_dict())

        return await asyncio.wait_for(future, timeout=30.0)

    async def _receive_loop(self) -> None:
        assert self._consumer is not None
        try:
            async for message in self._consumer:
                data = message.value
                try:
                    envelope = Envelope.from_dict(data)
                except Exception:
                    continue

                if envelope.type == MessageType.RESPONSE:
                    fut = self._pending.pop(envelope.id, None)
                    if fut and not fut.done():
                        fut.set_result(envelope.payload or {})
        except asyncio.CancelledError:
            pass


class KafkaTransport(Transport):
    """Kafka transport.

    Example::

        from microapi.transport.kafka import KafkaTransport

        app.run(transport=KafkaTransport(bootstrap_servers="kafka:9092"))
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        request_topic: str = _DEFAULT_REQUEST_TOPIC,
        response_topic: str = _DEFAULT_RESPONSE_TOPIC,
        group_id: str = "microapi-server",
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.request_topic = request_topic
        self.response_topic = response_topic
        self.group_id = group_id

    def create_server(self) -> TransportServer:
        return KafkaServer(
            bootstrap_servers=self.bootstrap_servers,
            request_topic=self.request_topic,
            response_topic=self.response_topic,
            group_id=self.group_id,
        )

    def create_client(self) -> TransportClient:
        return KafkaClient(
            bootstrap_servers=self.bootstrap_servers,
            request_topic=self.request_topic,
            response_topic=self.response_topic,
        )
