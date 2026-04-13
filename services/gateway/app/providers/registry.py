from __future__ import annotations

from collections.abc import Callable, Sequence
from threading import RLock
from time import monotonic

from services.gateway.app.providers.models import GatewayProvider
from shared.errors import ProviderUnavailableError

ProviderFetcher = Callable[[], list[GatewayProvider]]


class ProviderRegistry:
    def __init__(
        self,
        providers: Sequence[GatewayProvider],
        *,
        fetch_providers: ProviderFetcher | None = None,
        refresh_seconds: float = 5.0,
    ) -> None:
        self._lock = RLock()
        self._providers = _sorted_providers(providers)
        self._fetch_providers = fetch_providers
        self._refresh_seconds = max(refresh_seconds, 0.0)
        self._last_refresh_at = 0.0

    def list_providers(self) -> list[GatewayProvider]:
        self.refresh_if_needed()
        with self._lock:
            return list(self._providers)

    def list_enabled_providers(self) -> list[GatewayProvider]:
        return [provider for provider in self.list_providers() if provider.enabled]

    def list_supported_models(self) -> list[str]:
        models: list[str] = []
        for provider in self.list_enabled_providers():
            for model in provider.supported_models:
                if model not in models:
                    models.append(model)
        return models

    def primary_provider(self) -> GatewayProvider | None:
        enabled = self.list_enabled_providers()
        if not enabled:
            return None
        return enabled[0]

    def candidates_for_model(self, model: str) -> list[GatewayProvider]:
        return [
            provider
            for provider in self.list_enabled_providers()
            if model in provider.supported_models
        ]

    def get_provider(self, provider_id: str) -> GatewayProvider | None:
        for provider in self.list_providers():
            if provider.provider_id == provider_id:
                return provider
        return None

    def refresh_if_needed(self, *, force: bool = False) -> None:
        fetch = self._fetch_providers
        if fetch is None:
            return

        now = monotonic()
        with self._lock:
            has_cached = bool(self._providers)
            refresh_due = force or not has_cached
            if not refresh_due:
                refresh_due = self._refresh_seconds == 0.0
            if not refresh_due:
                refresh_due = (now - self._last_refresh_at) >= self._refresh_seconds

        if not refresh_due:
            return

        try:
            fresh = _sorted_providers(fetch())
        except Exception as exc:
            with self._lock:
                if self._providers:
                    return
            raise ProviderUnavailableError(
                "Failed to refresh providers from registry",
                details={"error_type": type(exc).__name__},
            ) from exc

        if not fresh:
            with self._lock:
                if self._providers:
                    return
            raise ProviderUnavailableError("Provider registry returned no providers")

        with self._lock:
            self._providers = fresh
            self._last_refresh_at = now


def _sorted_providers(providers: Sequence[GatewayProvider]) -> list[GatewayProvider]:
    return sorted(providers, key=lambda provider: (provider.priority, provider.provider_id))
