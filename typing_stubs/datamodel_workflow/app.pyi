"""Static interface for DMW's exported ASGI application."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

class ASGIApplication(Protocol):
    """Minimal callable contract consumed by the experiment launcher."""

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None: ...

app: ASGIApplication
