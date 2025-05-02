from functools import wraps
from typing import Callable, Awaitable, TypeVar, ParamSpec, AsyncGenerator, Union
from types import AsyncGeneratorType
import inspect

from pydantic import BaseModel

P = ParamSpec("P")
R = TypeVar("R")

MethodFunc = Callable[P, Union[Awaitable[R], AsyncGenerator[R, None]]]
Decorator = Callable[[MethodFunc], MethodFunc]


class Method(BaseModel):
    func: MethodFunc
    streaming: bool


class Service:
    def __init__(self, name: str):
        self.name = name
        self.methods: dict[str, Method] = {}

    def method(self) -> Decorator:
        def decorator(func: MethodFunc) -> MethodFunc:
            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs):
                result = func(*args, **kwargs)
                if inspect.isasyncgen(result):
                    return result
                return await result

            sig = inspect.signature(func)
            return_annotation = sig.return_annotation
            is_streaming = (
                return_annotation is not inspect.Signature.empty
                and hasattr(return_annotation, "__origin__")
                and return_annotation.__origin__ in (AsyncGenerator, AsyncGeneratorType)
            )

            self.methods[func.__name__] = Method(func=wrapper, streaming=is_streaming)
            return wrapper

        return decorator
