"""
SubQ Savant over Chat Completions.

Transport is httpx. Requests go only to the configured base URL, which
``normalize_subq_base_url`` has already restricted to https://api.subq.ai/v1.
Redirects are not followed, so a 3xx cannot move the bearer token to another host.
``trust_env`` is off so HTTP(S)_PROXY cannot redirect the token either.

Savant is stateless here: one completion per call, no tools, no files, no
conversation ids, ``store: false``. SubQ Snap's Decisions API is not called.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.services.llm.config import APPROVED_SUBQ_HOST, REASONING_EFFORT, SubQConfig, load_subq_config
from app.services.llm.errors import (
    AuthenticationError,
    ConfigurationError,
    InsufficientCreditsError,
    MalformedResponseError,
    ModelAccessDeniedError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    TransientProviderError,
    TruncatedResponseError,
    UnexpectedModelError,
    UnexpectedRedirectError,
)
from app.services.llm.schemas import RESPONSE_FORMAT, Completion, TokenUsage

# Tests inject this. Production leaves it None and uses the network.
transport_override: httpx.BaseTransport | None = None

_MAX_RESPONSE_BYTES = 1_000_000
_TRANSIENT_STATUS = {429, 502, 503, 504, 529}
_RETRYABLE = (RateLimitError, TransientProviderError, ProviderTimeoutError)

Sleep = Callable[[float], None]


class SubQProvider:
    name = "subq"

    def __init__(
        self,
        config: SubQConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        allow_live: bool = False,
        sleep: Sleep = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._transport = transport if transport is not None else transport_override
        self._allow_live = allow_live
        self._sleep = sleep
        self._monotonic = monotonic

    @classmethod
    def from_settings(cls, *, allow_live: bool = False, require_key: bool = True) -> "SubQProvider":
        return cls(load_subq_config(settings, require_key=require_key), allow_live=allow_live)

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = RESPONSE_FORMAT,
    ) -> Completion:
        self._refuse_live_from_tests()
        started = self._monotonic()
        deadline = started + self.config.timeout_seconds * (self.config.max_retries + 1)
        attempts = 0
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise ProviderTimeoutError("timeout", attempts=max(attempts, 1), latency_ms=self._elapsed(started))
            attempts += 1
            try:
                return self._once(
                    messages,
                    timeout=min(self.config.timeout_seconds, remaining),
                    attempts=attempts,
                    started=started,
                    response_format=response_format,
                )
            except _RETRYABLE as exc:
                exc.attempts = attempts
                exc.latency_ms = self._elapsed(started)
                if attempts > self.config.max_retries:
                    raise
                pause = min(self.config.retry_backoff_seconds, max(0.0, deadline - self._monotonic()))
                if pause > 0:
                    self._sleep(pause)

    def complete_text(self, messages: list[dict[str, Any]]) -> Completion:
        """Minimal completion with no schema. Used by the synthetic preflight only."""
        return self.complete(messages, response_format=None)

    def list_models(self) -> list[str]:
        """GET /v1/models. Ids available to this key; early-access models are omitted when locked."""
        self._refuse_live_from_tests()
        started = self._monotonic()
        response = self._send("GET", self.config.models_url, None, timeout=self.config.timeout_seconds)
        self._raise_for_status(response, attempts=1, started=started)
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise MalformedResponseError("malformed_response", status=response.status_code) from exc
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise MalformedResponseError("malformed_response", status=response.status_code)
        ids: list[str] = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.append(item["id"])
        return ids

    def _once(
        self,
        messages: list[dict[str, Any]],
        *,
        timeout: float,
        attempts: int,
        started: float,
        response_format: dict[str, Any] | None,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_output_tokens,
            "reasoning_effort": REASONING_EFFORT,
            "store": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        response = self._send("POST", self.config.chat_completions_url, payload, timeout=timeout)
        self._raise_for_status(response, attempts=attempts, started=started)
        return self._parse(response, attempts=attempts, started=started)

    def _send(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        *,
        timeout: float,
    ) -> httpx.Response:
        if not _approved_url(url):
            raise ConfigurationError("subq_base_url_rejected")
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=httpx.Timeout(timeout),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.request(method, url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("timeout") from exc
        except httpx.TransportError as exc:
            raise TransientProviderError("transport_error") from exc
        if response.is_redirect or 300 <= response.status_code < 400:
            raise UnexpectedRedirectError("unexpected_redirect", status=response.status_code)
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise MalformedResponseError("malformed_response", status=response.status_code)
        return response

    def _raise_for_status(self, response: httpx.Response, *, attempts: int, started: float) -> None:
        if response.status_code < 400:
            return
        code = _error_code(response)
        status = response.status_code
        latency_ms = self._elapsed(started)
        if status == 401 or code == "invalid_api_key":
            raise AuthenticationError("invalid_api_key", status=status, attempts=attempts, latency_ms=latency_ms)
        if status == 402 or code == "insufficient_credits":
            raise InsufficientCreditsError("insufficient_credits", status=status, attempts=attempts, latency_ms=latency_ms)
        if status == 403 or code == "model_not_allowed":
            raise ModelAccessDeniedError("model_not_allowed", status=status, attempts=attempts, latency_ms=latency_ms)
        if status == 429:
            raise RateLimitError(code or "rate_limit_exceeded", status=status, attempts=attempts, latency_ms=latency_ms)
        if status in _TRANSIENT_STATUS:
            raise TransientProviderError(code or "transient_error", status=status, attempts=attempts, latency_ms=latency_ms)
        if code in ("validation_error", "unsupported_parameter", "unsupported_value", "context_length_exceeded"):
            raise MalformedResponseError(code, status=status, attempts=attempts, latency_ms=latency_ms)
        raise ProviderError(code or "provider_rejected", status=status, attempts=attempts, latency_ms=latency_ms)

    def _parse(self, response: httpx.Response, *, attempts: int, started: float) -> Completion:
        latency = self._elapsed(started)
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise MalformedResponseError(
                "malformed_response", status=response.status_code, attempts=attempts, latency_ms=latency
            ) from exc
        if not isinstance(body, dict):
            raise MalformedResponseError("malformed_response", attempts=attempts, latency_ms=latency)
        model = body.get("model")
        if model is not None and model != self.config.model:
            raise UnexpectedModelError("unexpected_model", attempts=attempts, latency_ms=latency)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise MalformedResponseError("malformed_response", attempts=attempts, latency_ms=latency)
        choice = choices[0]
        raw_message = choice.get("message")
        message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
        if message.get("tool_calls"):
            raise MalformedResponseError("malformed_response", attempts=attempts, latency_ms=latency)
        content = message.get("content")
        if choice.get("finish_reason") == "length" or not isinstance(content, str) or not content.strip():
            raise TruncatedResponseError("truncated", attempts=attempts, latency_ms=latency)
        if len(content) > 20_000:
            raise MalformedResponseError("malformed_response", attempts=attempts, latency_ms=latency)
        return Completion(
            content=content,
            model=model if isinstance(model, str) else None,
            usage=_usage(body.get("usage")),
            latency_ms=latency,
            attempts=attempts,
        )

    def _refuse_live_from_tests(self) -> None:
        if self._transport is None and settings.ENVIRONMENT == "test" and not self._allow_live:
            raise ConfigurationError("live_calls_disabled_in_tests")

    def _elapsed(self, started: float) -> float:
        return (self._monotonic() - started) * 1000.0


def _approved_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != APPROVED_SUBQ_HOST or parsed.port not in (None, 443):
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    return parsed.path in ("/v1/chat/completions", "/v1/models")


def _error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except json.JSONDecodeError:
        return ""
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    return ""


def _usage(raw: Any) -> TokenUsage:
    if not isinstance(raw, dict):
        return TokenUsage()
    prompt_raw = raw.get("prompt_tokens_details")
    completion_raw = raw.get("completion_tokens_details")
    prompt_details = prompt_raw if isinstance(prompt_raw, dict) else {}
    completion_details = completion_raw if isinstance(completion_raw, dict) else {}
    return TokenUsage(
        prompt_tokens=_as_int(raw.get("prompt_tokens")),
        completion_tokens=_as_int(raw.get("completion_tokens")),
        reasoning_tokens=_as_int(completion_details.get("reasoning_tokens")),
        cached_tokens=_as_int(prompt_details.get("cached_tokens")),
    )


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
