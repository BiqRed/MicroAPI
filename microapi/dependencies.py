"""FastAPI-style dependency injection system."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from microapi.exceptions import DependencyError

if TYPE_CHECKING:
    from microapi.protocol import Request


class _Depends:
    """Marker object returned by :func:`Depends`."""

    __slots__ = ("dependency", "use_cache")

    def __init__(self, dependency: Callable[..., Any], *, use_cache: bool = True) -> None:
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        attr = getattr(self.dependency, "__name__", repr(self.dependency))
        return f"Depends({attr})"


def Depends(dependency: Callable[..., Any], *, use_cache: bool = True) -> Any:  # noqa: N802
    """Declare a dependency, resolved at call time.

    Usage::

        async def get_db():
            return await create_connection()

        @service.method
        async def get_user(
            payload: GetUserPayload,
            db: Connection = Depends(get_db),
        ) -> User:
            ...
    """
    return _Depends(dependency, use_cache=use_cache)


class DependencyResolver:
    """Resolves dependency trees for a single request scope."""

    async def resolve(
        self,
        dependencies: dict[str, _Depends],
        request: Request,
    ) -> dict[str, Any]:
        """Resolve all *dependencies* and return name->value mapping."""
        resolved: dict[str, Any] = {}
        cache: dict[int, Any] = {}  # id(callable) -> result

        for name, dep in dependencies.items():
            dep_id = id(dep.dependency)

            if dep.use_cache and dep_id in cache:
                resolved[name] = cache[dep_id]
                continue

            try:
                result = await self._call_dependency(dep.dependency, request)
            except Exception as exc:
                raise DependencyError(f"Failed to resolve dependency '{name}': {exc}") from exc

            if dep.use_cache:
                cache[dep_id] = result
            resolved[name] = result

        return resolved

    async def _call_dependency(
        self,
        dependency: Callable[..., Any],
        request: Request,
    ) -> Any:
        """Call a single dependency callable, injecting *request* if accepted."""
        from microapi.protocol import Request as RequestType

        sig = inspect.signature(dependency)
        kwargs: dict[str, Any] = {}

        # Use get_type_hints to resolve string annotations from PEP 563
        try:
            hints = inspect.get_annotations(dependency, eval_str=True)
        except Exception:
            hints = {}

        for param_name in sig.parameters:
            ann = hints.get(param_name)
            if ann is not None and (ann is RequestType or (isinstance(ann, type) and issubclass(ann, RequestType))):
                kwargs[param_name] = request

        result = dependency(**kwargs)
        if inspect.isawaitable(result):
            result = await result

        return result
