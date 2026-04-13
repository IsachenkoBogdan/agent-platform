from __future__ import annotations

from threading import RLock


class LatencyTracker:
    def __init__(self, *, smoothing: float = 0.3) -> None:
        if not 0.0 < smoothing <= 1.0:
            raise ValueError("smoothing must be in (0.0, 1.0]")
        self._smoothing = smoothing
        self._lock = RLock()
        self._ewma_seconds: dict[str, float] = {}

    def record_success(self, *, provider_id: str, latency_seconds: float) -> None:
        latency = max(latency_seconds, 0.0)
        with self._lock:
            previous = self._ewma_seconds.get(provider_id)
            if previous is None:
                self._ewma_seconds[provider_id] = latency
                return
            self._ewma_seconds[provider_id] = (
                self._smoothing * latency + (1.0 - self._smoothing) * previous
            )

    def latency_seconds(self, *, provider_id: str) -> float | None:
        with self._lock:
            return self._ewma_seconds.get(provider_id)
