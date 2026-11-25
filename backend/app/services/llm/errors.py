"""Typed provider and grounding failures. Messages are stable codes, not provider bodies."""

from __future__ import annotations


class LLMError(Exception):
    """Base error. ``code`` is safe to log. It is not a provider response body."""

    def __init__(self, code: str, *, attempts: int = 1, latency_ms: float = 0.0) -> None:
        super().__init__(code)
        self.code = code
        self.attempts = attempts
        self.latency_ms = latency_ms


class ConfigurationError(LLMError):
    pass


class ProviderError(LLMError):
    def __init__(
        self,
        code: str,
        *,
        status: int | None = None,
        attempts: int = 1,
        latency_ms: float = 0.0,
    ) -> None:
        super().__init__(code, attempts=attempts, latency_ms=latency_ms)
        self.status = status


class AuthenticationError(ProviderError):
    pass


class InsufficientCreditsError(ProviderError):
    pass


class ModelAccessDeniedError(ProviderError):
    pass


class RateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class TransientProviderError(ProviderError):
    pass


class MalformedResponseError(ProviderError):
    pass


class TruncatedResponseError(ProviderError):
    pass


class UnexpectedModelError(ProviderError):
    pass


class UnexpectedRedirectError(ProviderError):
    pass


class GroundingError(LLMError):
    """Local rejection of a model payload. The template explanation is used instead."""
