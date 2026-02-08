"""Validation utilities for configuration values."""

from __future__ import annotations

import ipaddress
import re

from microapi.exceptions import ConfigurationError

_HOSTNAME_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*$"
)


def validate_host(host: str) -> str:
    """Validate and return a host string (IP address or hostname)."""
    if not host:
        raise ConfigurationError("Host must not be empty")

    # Try parsing as IP address first
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass

    # Validate as hostname
    if _HOSTNAME_RE.match(host) or host == "localhost":
        return host

    raise ConfigurationError(f"Invalid host: {host!r}")


def validate_port(port: int) -> int:
    """Validate and return a port number (1-65535)."""
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ConfigurationError(f"Port must be an integer between 1 and 65535, got {port!r}")
    return port
