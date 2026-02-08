"""Protobuf file generator.

Converts MicroAPI service / schema definitions into ``.proto`` files
for cross-language gRPC interop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from microapi._logging import get_logger
from microapi.protocol import MethodType
from microapi.service import MethodInfo, Service

logger = get_logger("generator.protobuf")

# ---- Type mapping --------------------------------------------------------

_PROTO_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "int64",
    float: "double",
    bool: "bool",
    bytes: "bytes",
}


def _proto_type(annotation: Any) -> str:
    """Map a Python type annotation to a protobuf type string."""
    if annotation in _PROTO_TYPE_MAP:
        return _PROTO_TYPE_MAP[annotation]

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is list and args:
        inner = _proto_type(args[0])
        return f"repeated {inner}"

    if origin is dict and len(args) == 2:
        k = _proto_type(args[0])
        v = _proto_type(args[1])
        return f"map<{k}, {v}>"

    # Union/Optional: pick the non-None type
    import types as _types

    if origin is _types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _proto_type(non_none[0])

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__

    return "string"  # fallback


def _is_repeated(proto_type: str) -> bool:
    return proto_type.startswith("repeated ")


def _clean_proto_type(proto_type: str) -> str:
    return proto_type.removeprefix("repeated ")


# ---- Message / Service generation ----------------------------------------


def _generate_message(name: str, model: type[BaseModel]) -> str:
    """Generate a protobuf ``message`` block from a Pydantic model."""
    lines = [f"message {name} {{"]
    hints = get_type_hints(model)
    fields = model.model_fields

    for idx, (field_name, field_info) in enumerate(fields.items(), start=1):
        ann = hints.get(field_name, str)
        proto = _proto_type(ann)

        # Handle optional fields
        is_optional = not field_info.is_required()
        if _is_repeated(proto):
            lines.append(f"  {proto} {field_name} = {idx};")
        elif is_optional:
            lines.append(f"  optional {_clean_proto_type(proto)} {field_name} = {idx};")
        else:
            lines.append(f"  {proto} {field_name} = {idx};")

    lines.append("}")
    return "\n".join(lines)


def _generate_service_proto(service: Service) -> str:
    """Generate a protobuf ``service`` block from a MicroAPI Service."""
    lines = [f"service {service.name.capitalize()}Service {{"]

    for method_info in service.methods.values():
        input_name = method_info.input_type.__name__ if method_info.input_type else "Empty"
        output_name = (
            method_info.output_type.__name__
            if method_info.output_type and isinstance(method_info.output_type, type)
            else "Empty"
        )

        if method_info.stream_input_type and isinstance(method_info.stream_input_type, type):
            stream_in_name = method_info.stream_input_type.__name__
        else:
            stream_in_name = input_name

        # gRPC method signature with streaming annotations
        if method_info.method_type == MethodType.UNARY:
            lines.append(f"  rpc {method_info.generated_name}({input_name}) returns ({output_name});")
        elif method_info.method_type == MethodType.SERVER_STREAMING:
            lines.append(f"  rpc {method_info.generated_name}({input_name}) returns (stream {output_name});")
        elif method_info.method_type == MethodType.CLIENT_STREAMING:
            lines.append(f"  rpc {method_info.generated_name}(stream {stream_in_name}) returns ({output_name});")
        elif method_info.method_type == MethodType.BIDI_STREAMING:
            lines.append(
                f"  rpc {method_info.generated_name}(stream {stream_in_name}) returns (stream {output_name});"
            )

    lines.append("}")
    return "\n".join(lines)


# ---- Main generator entry point -----------------------------------------


def generate_proto_files(services: dict[str, Service], output_dir: Path) -> None:
    """Generate ``.proto`` files from MicroAPI service definitions.

    One ``.proto`` file is created per service, containing:
    - All message types used by the service
    - The service definition with RPC methods
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for svc_name, service in services.items():
        # Collect messages
        messages: dict[str, type[BaseModel]] = {}
        for method_info in service.methods.values():
            if method_info.input_type and method_info.input_type.__name__ not in messages:
                messages[method_info.input_type.__name__] = method_info.input_type
            if (
                method_info.output_type
                and isinstance(method_info.output_type, type)
                and issubclass(method_info.output_type, BaseModel)
                and method_info.output_type.__name__ not in messages
            ):
                messages[method_info.output_type.__name__] = method_info.output_type
            if (
                method_info.stream_input_type
                and isinstance(method_info.stream_input_type, type)
                and issubclass(method_info.stream_input_type, BaseModel)
                and method_info.stream_input_type.__name__ not in messages
            ):
                messages[method_info.stream_input_type.__name__] = method_info.stream_input_type

        # Build .proto file
        proto_lines = [
            'syntax = "proto3";',
            "",
            f'package {svc_name};',
            "",
            f'option go_package = "./{svc_name}pb";',
            "",
        ]

        # Empty message (for methods with no input/output)
        needs_empty = any(
            m.input_type is None
            or (m.output_type is None)
            or (m.method_type in (MethodType.CLIENT_STREAMING, MethodType.BIDI_STREAMING) and m.input_type is None)
            for m in service.methods.values()
        )
        if needs_empty:
            proto_lines.append("message Empty {}")
            proto_lines.append("")

        for msg_name, model in messages.items():
            proto_lines.append(_generate_message(msg_name, model))
            proto_lines.append("")

        proto_lines.append(_generate_service_proto(service))
        proto_lines.append("")

        proto_path = output_dir / f"{svc_name}.proto"
        proto_path.write_text("\n".join(proto_lines), encoding="utf-8")

    logger.info("Generated %d .proto file(s) in %s", len(services), output_dir)
