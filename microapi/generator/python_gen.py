"""Python client library generator.

Introspects registered services and produces fully-typed Python modules
that can be imported and called like regular async functions.
"""

from __future__ import annotations

import inspect
import textwrap
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from microapi._logging import get_logger
from microapi.protocol import MethodType
from microapi.service import MethodInfo, Service

logger = get_logger("generator")

# ---- Type mapping helpers -----------------------------------------------

_BUILTIN_TYPE_MAP: dict[type, str] = {
    str: "str",
    int: "int",
    float: "float",
    bool: "bool",
    bytes: "bytes",
    type(None): "None",
}


def _python_type_str(annotation: Any) -> str:
    """Convert a type annotation to its string representation."""
    if annotation is None or annotation is type(None):
        return "None"

    if annotation in _BUILTIN_TYPE_MAP:
        return _BUILTIN_TYPE_MAP[annotation]

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is list:
        inner = _python_type_str(args[0]) if args else "Any"
        return f"list[{inner}]"
    if origin is dict:
        k = _python_type_str(args[0]) if args else "str"
        v = _python_type_str(args[1]) if len(args) > 1 else "Any"
        return f"dict[{k}, {v}]"
    if origin is set:
        inner = _python_type_str(args[0]) if args else "Any"
        return f"set[{inner}]"
    if origin is tuple:
        if args:
            parts = ", ".join(_python_type_str(a) for a in args)
            return f"tuple[{parts}]"
        return "tuple"

    # Union / Optional (X | None)
    import types as _types

    if origin is _types.UnionType:
        parts = [_python_type_str(a) for a in args]
        return " | ".join(parts)

    # Try typing.Union
    try:
        import typing

        if origin is typing.Union:
            parts = [_python_type_str(a) for a in args]
            return " | ".join(parts)
    except Exception:
        pass

    if isinstance(annotation, type):
        return annotation.__name__

    return str(annotation)


# ---- Schema introspection -----------------------------------------------


def _collect_schemas(services: dict[str, Service]) -> dict[str, type[BaseModel]]:
    """Gather all unique Pydantic schemas used by services."""
    schemas: dict[str, type[BaseModel]] = {}
    for service in services.values():
        for method_info in service.methods.values():
            if method_info.input_type and method_info.input_type.__name__ not in schemas:
                schemas[method_info.input_type.__name__] = method_info.input_type
            if method_info.output_type:
                if isinstance(method_info.output_type, type) and issubclass(method_info.output_type, BaseModel):
                    if method_info.output_type.__name__ not in schemas:
                        schemas[method_info.output_type.__name__] = method_info.output_type
            if method_info.stream_input_type:
                if isinstance(method_info.stream_input_type, type) and issubclass(
                    method_info.stream_input_type, BaseModel
                ):
                    if method_info.stream_input_type.__name__ not in schemas:
                        schemas[method_info.stream_input_type.__name__] = method_info.stream_input_type
    return schemas


def _generate_schema_class(name: str, model: type[BaseModel]) -> str:
    """Generate a ClientSchema class definition from a Pydantic model."""
    lines = [f"class {name}(ClientSchema):"]

    fields = model.model_fields
    if not fields:
        lines.append("    pass")
        return "\n".join(lines)

    hints = get_type_hints(model)

    for field_name, field_info in fields.items():
        ann = hints.get(field_name, Any)
        type_str = _python_type_str(ann)

        if field_info.is_required():
            lines.append(f"    {field_name}: {type_str}")
        elif field_info.default is not None:
            try:
                # Avoid PydanticUndefined or sentinel objects
                default_repr = repr(field_info.default)
                if "Undefined" in default_repr or "PydanticUndefined" in default_repr:
                    lines.append(f"    {field_name}: {type_str} = None")
                else:
                    lines.append(f"    {field_name}: {type_str} = {default_repr}")
            except Exception:
                lines.append(f"    {field_name}: {type_str} = None")
        else:
            lines.append(f"    {field_name}: {type_str} = None")

    return "\n".join(lines)


# ---- Method code generation ---------------------------------------------


def _generate_unary_method(
    service_name: str,
    method_info: MethodInfo,
    schemas: dict[str, type[BaseModel]],
) -> str:
    """Generate an async function for a unary RPC method."""
    func_name = method_info.generated_name
    output_type = method_info.output_type

    # Build parameter list from input schema fields
    params: list[str] = []
    if method_info.input_type:
        hints = get_type_hints(method_info.input_type)
        fields = method_info.input_type.model_fields
        for field_name, field_info in fields.items():
            ann = hints.get(field_name, Any)
            type_str = _python_type_str(ann)
            if field_info.is_required():
                params.append(f"{field_name}: {type_str}")
            else:
                default_repr = repr(field_info.default) if field_info.default is not None else "None"
                params.append(f"{field_name}: {type_str} = {default_repr}")

    params_str = ", ".join(params)
    return_type = output_type.__name__ if output_type and isinstance(output_type, type) else "dict"

    # Build payload dict
    if method_info.input_type:
        field_names = list(method_info.input_type.model_fields.keys())
        payload_items = ", ".join(f'"{fn}": {fn}' for fn in field_names)
        payload_str = f"{{{payload_items}}}"
    else:
        payload_str = "{}"

    lines = [
        f"async def {func_name}({params_str}) -> {return_type}:",
        f'    """Call {service_name}.{method_info.name}."""',
        f"    conn = Connection.get_current()",
        f"    result = await conn.request(",
        f'        service="{service_name}",',
        f'        method="{method_info.name}",',
        f"        payload={payload_str},",
        f"    )",
        f"    return {return_type}.model_validate(result)" if return_type != "dict" else "    return result",
    ]
    return "\n".join(lines)


def _generate_server_streaming_method(
    service_name: str,
    method_info: MethodInfo,
    schemas: dict[str, type[BaseModel]],
) -> str:
    """Generate an async generator for a server-streaming method."""
    func_name = method_info.generated_name
    output_type = method_info.output_type

    params: list[str] = []
    if method_info.input_type:
        hints = get_type_hints(method_info.input_type)
        fields = method_info.input_type.model_fields
        for field_name, field_info in fields.items():
            ann = hints.get(field_name, Any)
            type_str = _python_type_str(ann)
            if field_info.is_required():
                params.append(f"{field_name}: {type_str}")
            else:
                default_repr = repr(field_info.default) if field_info.default is not None else "None"
                params.append(f"{field_name}: {type_str} = {default_repr}")

    params_str = ", ".join(params)
    item_type = output_type.__name__ if output_type and isinstance(output_type, type) else "dict"

    if method_info.input_type:
        field_names = list(method_info.input_type.model_fields.keys())
        payload_items = ", ".join(f'"{fn}": {fn}' for fn in field_names)
        payload_str = f"{{{payload_items}}}"
    else:
        payload_str = "{}"

    lines = [
        f"async def {func_name}({params_str}) -> AsyncIterator[{item_type}]:",
        f'    """Stream results from {service_name}.{method_info.name}."""',
        f"    conn = Connection.get_current()",
        f"    async for item in conn.request_stream(",
        f'        service="{service_name}",',
        f'        method="{method_info.name}",',
        f"        payload={payload_str},",
        f"    ):",
        f"        yield {item_type}.model_validate(item)" if item_type != "dict" else "        yield item",
    ]
    return "\n".join(lines)


def _generate_client_streaming_class(
    service_name: str,
    method_info: MethodInfo,
    schemas: dict[str, type[BaseModel]],
) -> str:
    """Generate a Stream class for client-streaming methods."""
    class_name = method_info.generated_name
    stream_type = method_info.stream_input_type

    # Build typed send() parameters
    send_params: list[str] = []
    if stream_type and isinstance(stream_type, type) and issubclass(stream_type, BaseModel):
        hints = get_type_hints(stream_type)
        fields = stream_type.model_fields
        for field_name, field_info in fields.items():
            ann = hints.get(field_name, Any)
            type_str = _python_type_str(ann)
            if field_info.is_required():
                send_params.append(f"{field_name}: {type_str}")
            else:
                default_repr = repr(field_info.default) if field_info.default is not None else "None"
                send_params.append(f"{field_name}: {type_str} = {default_repr}")

    send_params_str = ", ".join(send_params)
    type_name = stream_type.__name__ if stream_type and isinstance(stream_type, type) else "dict"

    if stream_type and isinstance(stream_type, type) and issubclass(stream_type, BaseModel):
        field_names = list(stream_type.model_fields.keys())
        payload_items = ", ".join(f"{fn}={fn}" for fn in field_names)
        send_body = f"        await self._send_raw({type_name}({payload_items}).model_dump())"
    else:
        send_body = "        await self._send_raw({})"

    lines = [
        f"class {class_name}(ClientStream):",
        f'    """Client stream for {service_name}.{method_info.name}."""',
        f"",
        f"    def __init__(self) -> None:",
        f"        conn = Connection.get_current()",
        f'        super().__init__(service="{service_name}", method="{method_info.name}", transport=conn.transport)',
        f"",
        f"    async def send(self, {send_params_str}) -> None:",
        f'        """Send a message to the server."""',
        send_body,
        f"",
        f"    async def end(self) -> None:",
        f'        """Signal end of stream."""',
        f"        await super().end()",
    ]
    return "\n".join(lines)


def _generate_bidi_streaming_class(
    service_name: str,
    method_info: MethodInfo,
    schemas: dict[str, type[BaseModel]],
) -> str:
    """Generate a BiStream class for bidirectional streaming methods."""
    class_name = method_info.generated_name
    stream_type = method_info.stream_input_type
    output_type = method_info.output_type

    send_params: list[str] = []
    if stream_type and isinstance(stream_type, type) and issubclass(stream_type, BaseModel):
        hints = get_type_hints(stream_type)
        fields = stream_type.model_fields
        for field_name, field_info in fields.items():
            ann = hints.get(field_name, Any)
            type_str = _python_type_str(ann)
            if field_info.is_required():
                send_params.append(f"{field_name}: {type_str}")
            else:
                default_repr = repr(field_info.default) if field_info.default is not None else "None"
                send_params.append(f"{field_name}: {type_str} = {default_repr}")

    send_params_str = ", ".join(send_params)
    in_type_name = stream_type.__name__ if stream_type and isinstance(stream_type, type) else "dict"
    out_type_name = output_type.__name__ if output_type and isinstance(output_type, type) else "dict"

    if stream_type and isinstance(stream_type, type) and issubclass(stream_type, BaseModel):
        field_names = list(stream_type.model_fields.keys())
        payload_items = ", ".join(f"{fn}={fn}" for fn in field_names)
        send_body = f"        await self._send_raw({in_type_name}({payload_items}).model_dump())"
    else:
        send_body = "        await self._send_raw({})"

    lines = [
        f"class {class_name}(ClientStream[{out_type_name}]):",
        f'    """Bidirectional stream for {service_name}.{method_info.name}."""',
        f"",
        f"    def __init__(self) -> None:",
        f"        conn = Connection.get_current()",
        f'        super().__init__(service="{service_name}", method="{method_info.name}", transport=conn.transport)',
        f"",
        f"    async def send(self, {send_params_str}) -> None:",
        f'        """Send a message to the server."""',
        send_body,
        f"",
        f"    async def next(self) -> {out_type_name} | None:",
        f'        """Receive next server message."""',
        f"        data = await super().next()",
        f"        if data is not None:",
        f"            return {out_type_name}.model_validate(data)" if out_type_name != "dict" else "            return data",
        f"        return None",
        f"",
        f"    async def end(self) -> None:",
        f'        """Signal end of stream."""',
        f"        await super().end()",
    ]
    return "\n".join(lines)


# ---- Main generator entry point -----------------------------------------


def generate_python_lib(services: dict[str, Service], output_dir: Path) -> None:
    """Generate a fully-typed Python client library from service definitions.

    Creates:
    - ``types.py`` — re-exported Pydantic schemas
    - ``{service_name}.py`` — one module per service with typed functions/classes
    - ``__init__.py`` — convenience re-exports
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all schemas
    all_schemas = _collect_schemas(services)

    # ---- types.py ----
    types_lines = [
        '"""Auto-generated schema types for MicroAPI client."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from microapi.client.base import ClientSchema",
        "",
    ]
    for name, model in all_schemas.items():
        types_lines.append("")
        types_lines.append(_generate_schema_class(name, model))
        types_lines.append("")

    (output_dir / "types.py").write_text("\n".join(types_lines), encoding="utf-8")

    # ---- per-service modules ----
    service_module_names: list[str] = []

    for svc_name, service in services.items():
        service_module_names.append(svc_name)
        module_lines = [
            f'"""Auto-generated client for the "{svc_name}" service."""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import Any, AsyncIterator",
            "",
            "from microapi.client.base import ClientSchema, Connection",
            "from microapi.client.stream import ClientStream",
            "",
            f"from .types import *  # noqa: F401,F403",
            "",
        ]

        # Import specific types used by this service
        used_types: set[str] = set()
        for method_info in service.methods.values():
            if method_info.output_type and isinstance(method_info.output_type, type):
                used_types.add(method_info.output_type.__name__)
            if method_info.stream_input_type and isinstance(method_info.stream_input_type, type):
                used_types.add(method_info.stream_input_type.__name__)

        for method_info in service.methods.values():
            module_lines.append("")
            if method_info.method_type == MethodType.UNARY:
                module_lines.append(_generate_unary_method(svc_name, method_info, all_schemas))
            elif method_info.method_type == MethodType.SERVER_STREAMING:
                module_lines.append(_generate_server_streaming_method(svc_name, method_info, all_schemas))
            elif method_info.method_type == MethodType.CLIENT_STREAMING:
                module_lines.append(_generate_client_streaming_class(svc_name, method_info, all_schemas))
            elif method_info.method_type == MethodType.BIDI_STREAMING:
                module_lines.append(_generate_bidi_streaming_class(svc_name, method_info, all_schemas))
            module_lines.append("")

        (output_dir / f"{svc_name}.py").write_text("\n".join(module_lines), encoding="utf-8")

    # ---- __init__.py ----
    init_lines = [
        '"""Auto-generated MicroAPI client library."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    for mod_name in service_module_names:
        init_lines.append(f"from . import {mod_name}")
    init_lines.append("from . import types")
    init_lines.append("")
    init_lines.append(f"__all__ = {[*service_module_names, 'types']!r}")
    init_lines.append("")

    (output_dir / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")

    logger.info(
        "Generated client library: %d service(s), %d schema(s) -> %s",
        len(services),
        len(all_schemas),
        output_dir,
    )
