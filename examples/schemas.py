from microapi import Scheme


class User(Scheme):
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    age: int | None = None


class GetUserPayload(Scheme):
    user_id: int
    fields: list[str] | None = None


class GetUsersPayload(Scheme):
    fields: list[str] | None = None
