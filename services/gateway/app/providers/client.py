from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from services.gateway.app.providers.models import GatewayProvider
from shared.contracts import ChatChoice, ChatCompletionRequest, ChatCompletionResponse, ChatUsage
from shared.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class ProviderStream:
    provider_id: str
    media_type: str
    stream_bytes: Callable[[], Iterator[bytes]]


class ProviderClient:
    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def chat_completion(
        self,
        *,
        provider: GatewayProvider,
        payload: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        headers = _build_headers(provider)
        body = payload.model_dump(mode="json", exclude_none=True)
        url = _completion_url(provider)

        try:
            with httpx.Client(
                timeout=provider.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"Provider timeout: {provider.provider_id}",
                details={"provider_id": provider.provider_id},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"Provider request failed: {provider.provider_id}",
                details={"provider_id": provider.provider_id},
            ) from exc

        _raise_for_provider_status(provider=provider, response=response)

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(
                f"Invalid provider response body: {provider.provider_id}",
                details={"provider_id": provider.provider_id},
            ) from exc

        return _parse_completion_response(
            data=data, provider=provider, fallback_model=payload.model
        )

    def stream_chat_completion(
        self,
        *,
        provider: GatewayProvider,
        payload: ChatCompletionRequest,
    ) -> ProviderStream:
        headers = _build_headers(provider)
        body = payload.model_dump(mode="json", exclude_none=True)
        url = _completion_url(provider)

        client = httpx.Client(timeout=provider.timeout_seconds, transport=self._transport)
        stream_context = client.stream("POST", url, json=body, headers=headers)

        try:
            response = stream_context.__enter__()
        except httpx.TimeoutException as exc:
            client.close()
            raise ProviderTimeoutError(
                f"Provider timeout: {provider.provider_id}",
                details={"provider_id": provider.provider_id},
            ) from exc
        except httpx.HTTPError as exc:
            client.close()
            raise ProviderUnavailableError(
                f"Provider request failed: {provider.provider_id}",
                details={"provider_id": provider.provider_id},
            ) from exc

        try:
            _raise_for_provider_status(provider=provider, response=response)
        except Exception:
            stream_context.__exit__(None, None, None)
            client.close()
            raise

        media_type = response.headers.get("content-type", "text/event-stream")
        closed = False

        def close_stream() -> None:
            nonlocal closed
            if closed:
                return
            closed = True
            stream_context.__exit__(None, None, None)
            client.close()

        def stream_bytes() -> Iterator[bytes]:
            try:
                for chunk in response.iter_raw():
                    if chunk:
                        yield chunk
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError(
                    f"Provider timeout: {provider.provider_id}",
                    details={"provider_id": provider.provider_id},
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError(
                    f"Provider stream failed: {provider.provider_id}",
                    details={"provider_id": provider.provider_id},
                ) from exc
            finally:
                close_stream()

        return ProviderStream(
            provider_id=provider.provider_id,
            media_type=media_type,
            stream_bytes=stream_bytes,
        )


def _build_headers(provider: GatewayProvider) -> dict[str, str]:
    headers: dict[str, str] = {"content-type": "application/json"}
    if provider.api_key:
        headers["authorization"] = f"Bearer {provider.api_key}"
    return headers


def _completion_url(provider: GatewayProvider) -> str:
    return f"{provider.base_url}/chat/completions"


def _raise_for_provider_status(*, provider: GatewayProvider, response: httpx.Response) -> None:
    if response.status_code >= 500 or response.status_code == 429:
        raise ProviderUnavailableError(
            f"Provider unavailable: {provider.provider_id}",
            details={"provider_id": provider.provider_id, "status_code": response.status_code},
        )

    if response.status_code >= 400:
        raise ProviderError(
            f"Provider rejected request: {provider.provider_id}",
            details={"provider_id": provider.provider_id, "status_code": response.status_code},
        )


def _parse_completion_response(
    *,
    data: dict[str, Any],
    provider: GatewayProvider,
    fallback_model: str,
) -> ChatCompletionResponse:
    raw_choices = data.get("choices")
    if not isinstance(raw_choices, list) or not raw_choices:
        raise ProviderError(
            f"Provider returned empty choices: {provider.provider_id}",
            details={"provider_id": provider.provider_id},
        )

    try:
        choices = [ChatChoice.model_validate(choice) for choice in raw_choices]
        usage_data = data.get("usage")
        usage = ChatUsage.model_validate(usage_data) if isinstance(usage_data, dict) else None
    except ValidationError as exc:
        raise ProviderError(
            f"Provider response validation failed: {provider.provider_id}",
            details={"provider_id": provider.provider_id},
        ) from exc

    response_id = data.get("id")
    if not isinstance(response_id, str) or not response_id.strip():
        response_id = f"chatcmpl-{provider.provider_id}-fallback"

    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        model = fallback_model

    return ChatCompletionResponse(
        id=response_id,
        provider_id=provider.provider_id,
        model=model,
        choices=choices,
        usage=usage,
    )
