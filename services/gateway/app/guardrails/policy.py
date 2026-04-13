from __future__ import annotations

from fastapi import Request

from services.gateway.app.guardrails.injection import PromptInjectionDetector
from services.gateway.app.guardrails.secrets import SecretLeakDetector
from shared.config import Settings
from shared.contracts import ChatCompletionRequest
from shared.errors import ConfigError, GuardrailViolation
from shared.logging import get_logger


class GuardrailPolicy:
    def __init__(
        self,
        *,
        enabled: bool = True,
        injection_detector: PromptInjectionDetector | None = None,
        secret_detector: SecretLeakDetector | None = None,
    ) -> None:
        self._enabled = enabled
        self._injection_detector = injection_detector
        self._secret_detector = secret_detector
        self._logger = get_logger("gateway.guardrails")

    @classmethod
    def from_settings(cls, settings: Settings) -> GuardrailPolicy:
        enabled = settings.guardrails_enabled
        return cls(
            enabled=enabled,
            injection_detector=PromptInjectionDetector()
            if enabled and settings.guardrails_injection_enabled
            else None,
            secret_detector=SecretLeakDetector()
            if enabled and settings.guardrails_secrets_enabled
            else None,
        )

    def enforce(self, payload: ChatCompletionRequest) -> None:
        if not self._enabled:
            return

        for message_index, message in enumerate(payload.messages):
            if self._injection_detector is not None:
                rule = self._injection_detector.detect(message.content)
                if rule is not None:
                    self._log_violation(
                        category="prompt_injection",
                        rule=rule,
                        message_index=message_index,
                        role=message.role,
                        model=payload.model,
                    )
                    raise GuardrailViolation(
                        "Request blocked by guardrails",
                        details={
                            "category": "prompt_injection",
                            "rule": rule,
                            "message_index": message_index,
                        },
                    )

            if self._secret_detector is not None:
                rule = self._secret_detector.detect(message.content)
                if rule is not None:
                    self._log_violation(
                        category="secret_leak",
                        rule=rule,
                        message_index=message_index,
                        role=message.role,
                        model=payload.model,
                    )
                    raise GuardrailViolation(
                        "Request blocked by guardrails",
                        details={
                            "category": "secret_leak",
                            "rule": rule,
                            "message_index": message_index,
                        },
                    )

    def _log_violation(
        self,
        *,
        category: str,
        rule: str,
        message_index: int,
        role: str,
        model: str,
    ) -> None:
        self._logger.warning(
            "guardrail_blocked",
            category=category,
            rule=rule,
            message_index=message_index,
            role=role,
            model=model,
        )


def get_guardrail_policy(request: Request) -> GuardrailPolicy:
    policy = getattr(request.app.state, "guardrail_policy", None)
    if not isinstance(policy, GuardrailPolicy):
        raise ConfigError("Guardrail policy is not initialized")
    return policy
