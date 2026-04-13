from __future__ import annotations

import concurrent.futures
import threading
import time

from services.registry.app.store import InMemoryRegistryStore
from shared.contracts import ProviderRecord
from shared.errors import RegistryConflictError


def _provider_payload() -> ProviderRecord:
    return ProviderRecord.model_validate(
        {
            "provider_id": "openrouter",
            "provider_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "supported_models": ["gpt-4o-mini"],
        }
    )


def test_store_create_provider_is_thread_safe(monkeypatch) -> None:
    store = InMemoryRegistryStore()
    provider = _provider_payload()

    original_model_copy = ProviderRecord.model_copy

    def delayed_model_copy(self: ProviderRecord, *args, **kwargs):
        time.sleep(0.01)
        return original_model_copy(self, *args, **kwargs)

    monkeypatch.setattr(ProviderRecord, "model_copy", delayed_model_copy)

    barrier = threading.Barrier(8)

    def attempt_create() -> str:
        barrier.wait(timeout=2)
        try:
            store.create_provider(provider)
        except RegistryConflictError:
            return "conflict"
        return "created"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: attempt_create(), range(8)))

    assert results.count("created") == 1
    assert results.count("conflict") == 7
