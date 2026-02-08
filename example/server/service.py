"""Users service definition with all 4 RPC method patterns."""

from microapi import Service, types

from schemas import GetUserPayload, GetUsersPayload, User

service = Service("users")


# -- Unary: request -> response -------------------------------------------

@service.method
async def get_user(payload: GetUserPayload) -> User:
    """Get a single user by ID."""
    # In real app, fetch from database
    return User(
        username="alice",
        firstname="Alice",
        lastname="Smith",
        age=30,
    )


# -- Server streaming: request -> stream of responses ---------------------

@service.method
async def get_users(payload: GetUsersPayload) -> types.Streaming[User]:
    """Stream all users."""
    users = [
        User(username="alice", firstname="Alice", age=30),
        User(username="bob", firstname="Bob", age=25),
        User(username="charlie", firstname="Charlie", age=35),
    ]
    for user in users:
        yield user


# -- Client streaming: stream of requests -> response --------------------

@service.method
async def add_users(stream: types.Stream[User]) -> None:
    """Receive a stream of users and persist them."""
    count = 0
    async for user in stream:
        # In real app, save to database
        print(f"  Saving user: {user.username}")
        count += 1
    print(f"  Total saved: {count}")


# -- Bidirectional streaming: stream <-> stream ---------------------------

@service.method(generated_name="create_return_user")
async def add_and_get_users(stream: types.Stream[User]) -> types.Streaming[User]:
    """Receive users, create them, and stream back the created versions."""
    async for user in stream:
        # Simulate creation with an enriched response
        created = User(
            username=user.username,
            firstname=user.firstname,
            lastname=user.lastname,
            age=user.age,
        )
        yield created
