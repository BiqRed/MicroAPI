
from microapi import Middleware


class AuthMiddleware(Middleware):
    async def __call__(self, message, call_next):
        print('AuthMiddleware')
        return await call_next(message)
