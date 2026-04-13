from __future__ import annotations

from collections.abc import Sequence
from threading import Lock

from services.gateway.app.providers.models import GatewayProvider


class RoundRobinBalancer:
    def __init__(self) -> None:
        self._lock = Lock()
        self._cursor: dict[str, int] = {}

    def order(self, *, model: str, providers: Sequence[GatewayProvider]) -> list[GatewayProvider]:
        if not providers:
            return []

        ordered = list(providers)
        with self._lock:
            start = self._cursor.get(model, 0) % len(ordered)
            self._cursor[model] = start + 1
        return ordered[start:] + ordered[:start]
