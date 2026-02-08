"""gRPC wire-format codec: length-prefixed message framing."""

from __future__ import annotations

import struct

HEADER_SIZE = 5  # 1 byte compressed-flag + 4 bytes message-length


def encode_message(payload: bytes, *, compressed: bool = False) -> bytes:
    """Encode *payload* into a gRPC length-prefixed frame.

    Wire format::

        1 byte  — compressed flag (0 or 1)
        4 bytes — message length (big-endian uint32)
        N bytes — message payload
    """
    flag = 1 if compressed else 0
    return struct.pack(">BI", flag, len(payload)) + payload


def decode_messages(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Decode as many complete gRPC frames as possible from *buffer*.

    Returns ``(messages, remaining_buffer)``.
    """
    messages: list[bytes] = []
    offset = 0
    while offset + HEADER_SIZE <= len(buffer):
        _flag, length = struct.unpack_from(">BI", buffer, offset)
        if offset + HEADER_SIZE + length > len(buffer):
            break  # incomplete message
        payload = buffer[offset + HEADER_SIZE : offset + HEADER_SIZE + length]
        messages.append(payload)
        offset += HEADER_SIZE + length
    return messages, buffer[offset:]
