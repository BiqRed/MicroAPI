"""Tests for microapi.utils.validators."""

from __future__ import annotations

import pytest

from microapi.exceptions import ConfigurationError
from microapi.utils.validators import validate_host, validate_port


class TestValidateHost:
    def test_valid_ipv4(self) -> None:
        assert validate_host("127.0.0.1") == "127.0.0.1"
        assert validate_host("0.0.0.0") == "0.0.0.0"

    def test_valid_hostname(self) -> None:
        assert validate_host("localhost") == "localhost"
        assert validate_host("example.com") == "example.com"

    def test_empty_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            validate_host("")

    def test_invalid_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            validate_host("not valid host!")


class TestValidatePort:
    def test_valid_ports(self) -> None:
        assert validate_port(80) == 80
        assert validate_port(443) == 443
        assert validate_port(1) == 1
        assert validate_port(65535) == 65535

    def test_zero_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            validate_port(0)

    def test_negative_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            validate_port(-1)

    def test_too_large_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            validate_port(65536)
