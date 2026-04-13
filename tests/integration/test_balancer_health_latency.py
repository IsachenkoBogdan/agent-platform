from __future__ import annotations

from services.gateway.app.balancer.health_aware import (
    HealthAndLatencyBalancer,
    ProviderHealthTracker,
)
from services.gateway.app.balancer.latency import LatencyTracker
from services.gateway.app.balancer.round_robin import RoundRobinBalancer
from services.gateway.app.providers.models import GatewayProvider
from shared.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _provider(provider_id: str) -> GatewayProvider:
    return GatewayProvider(
        provider_id=provider_id,
        provider_name=provider_id,
        base_url=f"https://{provider_id}.local/v1",
        supported_models=("model-x",),
        priority=100,
        enabled=True,
        api_key=None,
        timeout_seconds=10.0,
        input_per_1m_tokens_usd=0.0,
        output_per_1m_tokens_usd=0.0,
    )


def test_latency_aware_prefers_fast_provider() -> None:
    clock = FakeClock()
    balancer = HealthAndLatencyBalancer(
        round_robin=RoundRobinBalancer(),
        health=ProviderHealthTracker(ejection_seconds=15.0, clock=clock),
        latency=LatencyTracker(smoothing=1.0),
    )

    slow = _provider("slow")
    fast = _provider("fast")

    balancer.record_success(provider_id="slow", latency_seconds=1.2)
    balancer.record_success(provider_id="fast", latency_seconds=0.1)

    ordered = balancer.order(model="model-x", providers=[slow, fast])

    assert [provider.provider_id for provider in ordered] == ["fast", "slow"]


def test_timeout_ejection_removes_provider_from_candidate_order() -> None:
    clock = FakeClock()
    balancer = HealthAndLatencyBalancer(
        round_robin=RoundRobinBalancer(),
        health=ProviderHealthTracker(ejection_seconds=15.0, clock=clock),
        latency=LatencyTracker(smoothing=0.5),
    )

    a = _provider("a")
    b = _provider("b")

    balancer.record_failure(provider_id="a", error=ProviderTimeoutError("timeout"))
    ordered = balancer.order(model="model-x", providers=[a, b])

    assert [provider.provider_id for provider in ordered] == ["b"]
    assert balancer.is_ejected(provider_id="a") is True


def test_5xx_ejection_removes_provider_from_candidate_order() -> None:
    clock = FakeClock()
    balancer = HealthAndLatencyBalancer(
        round_robin=RoundRobinBalancer(),
        health=ProviderHealthTracker(ejection_seconds=15.0, clock=clock),
        latency=LatencyTracker(smoothing=0.5),
    )

    a = _provider("a")
    b = _provider("b")

    balancer.record_failure(provider_id="a", error=ProviderUnavailableError("unavailable"))
    ordered = balancer.order(model="model-x", providers=[a, b])

    assert [provider.provider_id for provider in ordered] == ["b"]
    assert balancer.is_ejected(provider_id="a") is True


def test_non_ejectable_error_does_not_eject_provider() -> None:
    clock = FakeClock()
    balancer = HealthAndLatencyBalancer(
        round_robin=RoundRobinBalancer(),
        health=ProviderHealthTracker(ejection_seconds=15.0, clock=clock),
        latency=LatencyTracker(smoothing=0.5),
    )

    balancer.record_failure(provider_id="a", error=ProviderError("bad request"))

    assert balancer.is_ejected(provider_id="a") is False


def test_recovery_reintroduces_provider_after_ejection_window() -> None:
    clock = FakeClock()
    balancer = HealthAndLatencyBalancer(
        round_robin=RoundRobinBalancer(),
        health=ProviderHealthTracker(ejection_seconds=5.0, clock=clock),
        latency=LatencyTracker(smoothing=0.5),
    )

    a = _provider("a")
    b = _provider("b")

    balancer.record_failure(provider_id="a", error=ProviderTimeoutError("timeout"))
    assert balancer.is_ejected(provider_id="a") is True

    clock.advance(5.1)

    ordered = balancer.order(model="model-x", providers=[a, b])
    ordered_ids = {provider.provider_id for provider in ordered}

    assert ordered_ids == {"a", "b"}
    assert balancer.is_ejected(provider_id="a") is False
