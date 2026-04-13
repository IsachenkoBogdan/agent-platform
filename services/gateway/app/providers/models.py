from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import ProviderRecord


@dataclass(frozen=True, slots=True)
class GatewayProvider:
    provider_id: str
    provider_name: str
    base_url: str
    supported_models: tuple[str, ...]
    priority: int
    enabled: bool
    api_key: str | None
    timeout_seconds: float
    input_per_1m_tokens_usd: float
    output_per_1m_tokens_usd: float

    @classmethod
    def from_record(
        cls,
        record: ProviderRecord,
        *,
        api_key: str | None,
        timeout_seconds: float,
    ) -> GatewayProvider:
        return cls(
            provider_id=record.provider_id,
            provider_name=record.provider_name,
            base_url=str(record.base_url).rstrip("/"),
            supported_models=tuple(record.supported_models),
            priority=record.priority,
            enabled=record.enabled,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            input_per_1m_tokens_usd=record.pricing.input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=record.pricing.output_per_1m_tokens_usd,
        )
