from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import structlog

_LOGGING_CONFIGURED = False


def _resolve_level(log_level: str) -> int:
    resolved_level = logging.getLevelName(log_level.upper())
    if isinstance(resolved_level, int):
        return resolved_level
    return logging.INFO


def setup_logging(log_level: str = "INFO") -> None:
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    level = _resolve_level(log_level)
    logging.basicConfig(level=level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _LOGGING_CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_context(**values: Any) -> None:
    structlog.contextvars.bind_contextvars(**values)


def unbind_context(*keys: str) -> None:
    structlog.contextvars.unbind_contextvars(*keys)


def safe_log_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}
