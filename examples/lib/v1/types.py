from microapi.client import BaseScheme


class User(BaseScheme):
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    age: int | None = None
