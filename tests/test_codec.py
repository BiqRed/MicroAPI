"""Tests for gRPC codec (wire format framing)."""

from __future__ import annotations

from microapi.transport.grpc.codec import decode_messages, encode_message


class TestGRPCCodec:
    def test_encode_decode_roundtrip(self) -> None:
        payload = b'{"name": "test"}'
        frame = encode_message(payload)

        messages, remaining = decode_messages(frame)
        assert len(messages) == 1
        assert messages[0] == payload
        assert remaining == b""

    def test_encode_format(self) -> None:
        payload = b"hello"
        frame = encode_message(payload)

        # 1 byte flag + 4 bytes length + payload
        assert len(frame) == 1 + 4 + len(payload)
        assert frame[0] == 0  # not compressed
        length = int.from_bytes(frame[1:5], "big")
        assert length == len(payload)

    def test_decode_multiple_messages(self) -> None:
        frame1 = encode_message(b"msg1")
        frame2 = encode_message(b"msg2")
        frame3 = encode_message(b"msg3")

        messages, remaining = decode_messages(frame1 + frame2 + frame3)
        assert len(messages) == 3
        assert messages[0] == b"msg1"
        assert messages[1] == b"msg2"
        assert messages[2] == b"msg3"
        assert remaining == b""

    def test_decode_incomplete_message(self) -> None:
        frame = encode_message(b"complete")
        # Truncate the frame
        partial = frame[:3]

        messages, remaining = decode_messages(partial)
        assert len(messages) == 0
        assert remaining == partial

    def test_decode_empty_buffer(self) -> None:
        messages, remaining = decode_messages(b"")
        assert messages == []
        assert remaining == b""

    def test_compressed_flag(self) -> None:
        payload = b"data"
        frame = encode_message(payload, compressed=True)
        assert frame[0] == 1  # compressed flag

    def test_large_payload(self) -> None:
        payload = b"x" * 100000
        frame = encode_message(payload)
        messages, remaining = decode_messages(frame)
        assert len(messages) == 1
        assert messages[0] == payload
