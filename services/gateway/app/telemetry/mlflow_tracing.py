from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from threading import Lock
from typing import Any

import mlflow


class MlflowTracer:
    def __init__(self, *, tracking_uri: str | None) -> None:
        self._tracking_uri = tracking_uri
        self._lock = Lock()
        self._configured = False

    @property
    def enabled(self) -> bool:
        return bool(self._tracking_uri)

    @contextmanager
    def span(
        self,
        name: str,
        *,
        span_type: str = "UNKNOWN",
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Any | None]:
        if not self.enabled:
            yield None
            return

        self._configure()
        with mlflow.start_span(name=name, span_type=span_type, attributes=attributes) as span:
            yield span

    def _configure(self) -> None:
        with self._lock:
            if self._configured:
                return
            assert self._tracking_uri is not None
            mlflow.set_tracking_uri(self._tracking_uri)
            self._configured = True
