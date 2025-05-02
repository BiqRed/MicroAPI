from microapi.client import Request, Stream, Streaming, BiStreaming

from .types import User


async def get_user(user_id: int, fields: list[str] | None = None) -> User:
    request = Request(service='users', method='get_user')
    response = await request(
        user_id=user_id,
        fields=fields
    )

    return User.model_validate(response.payload)


async def get_users(fields: list[str] | None = None) -> Streaming[User]:
    request = Request(service='users', method='get_users', streaming=True)

    async for user in request(fields=fields):
        yield User.model_validate(user)

    yield request.end()


class add_users(Stream):  # noqa: N801 pylint: disable=invalid-name
    def __init__(self):
        super().__init__(service='users', method='add_user')

    async def send(self, username: str | None = None, firstname: str | None = None, lastname: str | None = None, age: int | None = None) -> None:
        await super().send(User(username=username, firstname=firstname, lastname=lastname, age=age))


class create_return_user(Stream[User]):  # noqa: N801 pylint: disable=invalid-name
    def __init__(self):
        super().__init__(service='users', method='create_return_user')

    async def send(self, username: str | None = None, firstname: str | None = None, lastname: str | None = None, age: int | None = None) -> None:
        await super().send(User(username=username, firstname=firstname, lastname=lastname, age=age))
