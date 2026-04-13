from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from services.gateway.app.providers.models import GatewayProvider


class BalancerPolicy(Protocol):
    def order(self, *, model: str, providers: Sequence[GatewayProvider]) -> list[GatewayProvider]:
        """Return providers in preferred call order for this request."""
