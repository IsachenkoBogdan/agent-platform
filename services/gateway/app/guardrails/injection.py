from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InjectionRule:
    name: str
    pattern: re.Pattern[str]


class PromptInjectionDetector:
    def __init__(self, rules: tuple[InjectionRule, ...] | None = None) -> None:
        self._rules = rules or _default_rules()

    def detect(self, text: str) -> str | None:
        for rule in self._rules:
            if rule.pattern.search(text):
                return rule.name
        return None


def _default_rules() -> tuple[InjectionRule, ...]:
    return (
        InjectionRule(
            name="override_instructions",
            pattern=re.compile(
                r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above)\b.{0,40}"
                r"\b(instruction|prompt|message)s?\b",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        InjectionRule(
            name="reveal_system_prompt",
            pattern=re.compile(
                r"\b(reveal|show|print|dump|expose)\b.{0,40}\b(system|developer)\b.{0,40}"
                r"\b(prompt|instruction|message)s?\b",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        InjectionRule(
            name="jailbreak_phrase",
            pattern=re.compile(
                r"\b(jailbreak|dan mode|do anything now)\b",
                re.IGNORECASE,
            ),
        ),
    )
