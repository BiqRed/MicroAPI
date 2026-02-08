"""Tests for microapi.protocol."""

from __future__ import annotations

from microapi.protocol import (
    Envelope,
    MessageType,
    MethodType,
    Request,
    Response,
    StatusCode,
)


class TestRequest:
    def test_create_with_defaults(self) -> None:
        req = Request(service="users", method="get_user")
        assert req.service == "users"
        assert req.method == "get_user"
        assert req.payload is None
        assert isinstance(req.id, str)
        assert len(req.id) == 32  # hex uuid

    def test_create_with_payload(self) -> None:
        req = Request(service="s", method="m", payload={"key": "val"})
        assert req.payload == {"key": "val"}


class TestResponse:
    def test_default_status(self) -> None:
        resp = Response()
        assert resp.status_code == StatusCode.OK
        assert resp.error is None

    def test_error_response(self) -> None:
        resp = Response(error="not found", status_code=StatusCode.NOT_FOUND)
        assert resp.error == "not found"
        assert resp.status_code == StatusCode.NOT_FOUND


class TestEnvelope:
    def test_to_dict_roundtrip(self) -> None:
        env = Envelope(
            type=MessageType.REQUEST,
            service="users",
            method="get_user",
            payload={"user_id": 1},
            metadata={"token": "abc"},
        )
        d = env.to_dict()
        env2 = Envelope.from_dict(d)

        assert env2.type == MessageType.REQUEST
        assert env2.service == "users"
        assert env2.method == "get_user"
        assert env2.payload == {"user_id": 1}
        assert env2.metadata == {"token": "abc"}

    def test_from_dict_with_defaults(self) -> None:
        env = Envelope.from_dict({"type": "response"})
        assert env.type == MessageType.RESPONSE
        assert env.service == ""


class TestMethodType:
    def test_values(self) -> None:
        assert MethodType.UNARY.value == "unary"
        assert MethodType.SERVER_STREAMING.value == "server_streaming"
        assert MethodType.CLIENT_STREAMING.value == "client_streaming"
        assert MethodType.BIDI_STREAMING.value == "bidi_streaming"
