from abc import abstractmethod, ABC


class Middleware(ABC):
    @abstractmethod
    async def __call__(self, message, call_next):
        raise NotImplementedError
