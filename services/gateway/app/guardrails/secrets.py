from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SecretRule:
    name: str
    pattern: re.Pattern[str]


class SecretLeakDetector:
    def __init__(self, rules: tuple[SecretRule, ...] | None = None) -> None:
        self._rules = rules or _default_rules()

    def detect(self, text: str) -> str | None:
        for rule in self._rules:
            if rule.pattern.search(text):
                return rule.name
        return None


def _default_rules() -> tuple[SecretRule, ...]:
    return (
        SecretRule(
            name="openai_like_api_key",
            pattern=re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        ),
        SecretRule(
            name="aws_access_key_id",
            pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        ),
        SecretRule(
            name="private_key_material",
            pattern=re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ),
        SecretRule(
            name="generic_api_key_assignment",
            pattern=re.compile(
                r"\bapi[_-]?key\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}",
                re.IGNORECASE,
            ),
        ),
    )
