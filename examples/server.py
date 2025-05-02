from microapi import Service, types
from examples.schemas import GetUserPayload, GetUsersPayload, User
from examples.models import UserModel


service = Service('users')


@service.method
async def get_user(payload: GetUserPayload) -> User:
    user = await UserModel.get(payload.user_id)
    return User.model_validate(user)


@service.method
async def get_users(payload: GetUsersPayload) -> types.Streaming[User]:
    users = UserModel.all().fields(*payload.fields)

    async for user in users:
        yield User.model_validate(user)

    yield types.StreamingEnd


@service.method
async def add_users(stream: types.Stream[User]) -> None:
    async for user in stream:
        await UserModel.create(**user.model_dump())


@service.method(generated_name='create_return_user')
async def add_and_get_users(stream: types.Stream[User]) -> types.Streaming[User]:
    async for user in stream:
        created_user = await UserModel.create(**user.model_dump())
        yield created_user

    yield types.StreamingEnd
