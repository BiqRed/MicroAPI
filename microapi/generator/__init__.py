"""Code generation for MicroAPI client libraries and protobuf files."""

from __future__ import annotations

from microapi.generator.protobuf_gen import generate_proto_files
from microapi.generator.python_gen import generate_python_lib

__all__ = ["generate_python_lib", "generate_proto_files"]
