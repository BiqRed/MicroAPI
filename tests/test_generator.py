"""Tests for the code generator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from microapi import Schema, Service, types
from microapi.generator import generate_proto_files, generate_python_lib


class User(Schema):
    username: str | None = None
    firstname: str | None = None
    age: int | None = None


class GetUserPayload(Schema):
    user_id: int
    fields: list[str] | None = None


@pytest.fixture
def sample_service() -> Service:
    svc = Service("users")

    @svc.method
    async def get_user(payload: GetUserPayload) -> User:
        return User(username="test")

    @svc.method
    async def list_users(payload: GetUserPayload) -> types.Streaming[User]:
        yield User(username="test")

    @svc.method
    async def add_users(stream: types.Stream[User]) -> None:
        async for _ in stream:
            pass

    @svc.method(generated_name="create_return_user")
    async def bidi_users(stream: types.Stream[User]) -> types.Streaming[User]:
        async for user in stream:
            yield user

    return svc


class TestPythonGenerator:
    def test_generates_all_files(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "lib"
            generate_python_lib({"users": sample_service}, output)

            assert (output / "__init__.py").exists()
            assert (output / "types.py").exists()
            assert (output / "users.py").exists()

    def test_init_imports(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "lib"
            generate_python_lib({"users": sample_service}, output)

            init_content = (output / "__init__.py").read_text()
            assert "from . import users" in init_content
            assert "from . import types" in init_content

    def test_types_contains_schemas(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "lib"
            generate_python_lib({"users": sample_service}, output)

            types_content = (output / "types.py").read_text()
            assert "class User(ClientSchema):" in types_content
            assert "class GetUserPayload(ClientSchema):" in types_content

    def test_service_module_has_methods(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "lib"
            generate_python_lib({"users": sample_service}, output)

            users_content = (output / "users.py").read_text()
            assert "async def get_user(" in users_content
            assert "async def list_users(" in users_content
            assert "class add_users(" in users_content
            assert "class create_return_user(" in users_content

    def test_unary_method_signature(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "lib"
            generate_python_lib({"users": sample_service}, output)

            users_content = (output / "users.py").read_text()
            assert "user_id: int" in users_content
            assert ") -> User:" in users_content

    def test_streaming_class_has_send(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "lib"
            generate_python_lib({"users": sample_service}, output)

            users_content = (output / "users.py").read_text()
            assert "async def send(self" in users_content


class TestProtobufGenerator:
    def test_generates_proto_file(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "protos"
            generate_proto_files({"users": sample_service}, output)

            assert (output / "users.proto").exists()

    def test_proto_syntax(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "protos"
            generate_proto_files({"users": sample_service}, output)

            content = (output / "users.proto").read_text()
            assert 'syntax = "proto3";' in content
            assert "package users;" in content

    def test_proto_messages(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "protos"
            generate_proto_files({"users": sample_service}, output)

            content = (output / "users.proto").read_text()
            assert "message User {" in content
            assert "message GetUserPayload {" in content

    def test_proto_service(self, sample_service: Service) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "protos"
            generate_proto_files({"users": sample_service}, output)

            content = (output / "users.proto").read_text()
            assert "service UsersService {" in content
            assert "rpc get_user(" in content
            assert "returns (stream User)" in content  # server streaming
