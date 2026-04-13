from __future__ import annotations

from collections.abc import Callable, Sequence
from threading import RLock
from time import monotonic

from services.gateway.app.balancer.latency import LatencyTracker
from services.gateway.app.balancer.round_robin import RoundRobinBalancer
from services.gateway.app.providers.models import GatewayProvider
from shared.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError


class ProviderHealthTracker:
    def __init__(
        self,
        *,
        ejection_seconds: float = 15.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if ejection_seconds < 0.0:
            raise ValueError("ejection_seconds must be >= 0")

        self._ejection_seconds = ejection_seconds
        self._clock = clock or monotonic
        self._lock = RLock()
        self._ejected_until: dict[str, float] = {}

    def record_success(self, *, provider_id: str) -> None:
        with self._lock:
            self._ejected_until.pop(provider_id, None)

    def record_failure(self, *, provider_id: str, error: ProviderError) -> None:
        if not _is_ejectable_error(error):
            return

        with self._lock:
            self._ejected_until[provider_id] = self._clock() + self._ejection_seconds

    def is_ejected(self, *, provider_id: str) -> bool:
        with self._lock:
            until = self._ejected_until.get(provider_id)
        if until is None:
            return False
        if until > self._clock():
            return True

        with self._lock:
            current = self._ejected_until.get(provider_id)
            if current is not None and current <= self._clock():
                self._ejected_until.pop(provider_id, None)
        return False


class HealthAndLatencyBalancer:
    def __init__(
        self,
        *,
        round_robin: RoundRobinBalancer | None = None,
        health: ProviderHealthTracker | None = None,
        latency: LatencyTracker | None = None,
    ) -> None:
        self._round_robin = round_robin or RoundRobinBalancer()
        self._health = health or ProviderHealthTracker()
        self._latency = latency or LatencyTracker()

    def order(self, *, model: str, providers: Sequence[GatewayProvider]) -> list[GatewayProvider]:
        healthy = [
            provider
            for provider in providers
            if not self._health.is_ejected(provider_id=provider.provider_id)
        ]
        if not healthy:
            return []

        rr_ordered = self._round_robin.order(model=model, providers=healthy)
        rr_index = {provider.provider_id: index for index, provider in enumerate(rr_ordered)}

        return sorted(
            rr_ordered,
            key=lambda provider: (
                self._latency.latency_seconds(provider_id=provider.provider_id) or float("inf"),
                rr_index[provider.provider_id],
            ),
        )

    def record_success(self, *, provider_id: str, latency_seconds: float) -> None:
        self._health.record_success(provider_id=provider_id)
        self._latency.record_success(provider_id=provider_id, latency_seconds=latency_seconds)

    def record_failure(self, *, provider_id: str, error: ProviderError) -> None:
        self._health.record_failure(provider_id=provider_id, error=error)

    def is_ejected(self, *, provider_id: str) -> bool:
        return self._health.is_ejected(provider_id=provider_id)


def _is_ejectable_error(error: ProviderError) -> bool:
    return isinstance(error, ProviderTimeoutError | ProviderUnavailableError)
