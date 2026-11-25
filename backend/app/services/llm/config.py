"""Provider configuration. The approved SubQ host is fixed; callers cannot redirect it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.services.llm.errors import ConfigurationError

APPROVED_SUBQ_HOST = "api.subq.ai"
APPROVED_SUBQ_BASE = "https://api.subq.ai/v1"
# Savant always reasons, and max_tokens includes those reasoning tokens.
# "low" leaves room for the visible answer inside the configured output cap.
REASONING_EFFORT = "low"


@dataclass(frozen=True)
class SubQConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    max_output_tokens: int
    max_retries: int
    retry_backoff_seconds: float = 0.2

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.base_url}/models"


def normalize_subq_base_url(url: str) -> str:
    """Accept only https://api.subq.ai/v1. Rejects other hosts, credentials, and redirects-by-config."""
    parsed = urlsplit((url or "").strip())
    if parsed.scheme != "https":
        raise ConfigurationError("subq_base_url_rejected")
    if parsed.username or parsed.password:
        raise ConfigurationError("subq_base_url_rejected")
    if parsed.hostname != APPROVED_SUBQ_HOST:
        raise ConfigurationError("subq_base_url_rejected")
    if parsed.port not in (None, 443):
        raise ConfigurationError("subq_base_url_rejected")
    if parsed.path.rstrip("/") != "/v1":
        raise ConfigurationError("subq_base_url_rejected")
    if parsed.query or parsed.fragment:
        raise ConfigurationError("subq_base_url_rejected")
    return APPROVED_SUBQ_BASE


def validate_provider_settings(settings: Any) -> None:
    """Boot-time check. Does not print secrets. ``none`` skips SubQ checks."""
    provider = (settings.LLM_PROVIDER or "").strip().lower()
    if provider not in ("none", "subq"):
        raise RuntimeError("LLM_PROVIDER must be 'none' or 'subq'.")
    if provider != "subq":
        return
    try:
        normalize_subq_base_url(settings.SUBQ_BASE_URL)
    except ConfigurationError as exc:
        raise RuntimeError(
            "SUBQ_BASE_URL must be https://api.subq.ai/v1. Other hosts are rejected."
        ) from exc
    if not (settings.SUBQ_MODEL or "").strip():
        raise RuntimeError("SUBQ_MODEL is required when LLM_PROVIDER=subq.")
    timeout = settings.LLM_TIMEOUT_SECONDS
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < float(timeout) <= 120:
        raise RuntimeError("LLM_TIMEOUT_SECONDS must be greater than 0 and at most 120.")
    tokens = settings.LLM_MAX_OUTPUT_TOKENS
    if isinstance(tokens, bool) or not isinstance(tokens, int) or not 1 <= tokens <= 4096:
        raise RuntimeError("LLM_MAX_OUTPUT_TOKENS must be an integer from 1 to 4096.")
    retries = settings.LLM_MAX_RETRIES
    if isinstance(retries, bool) or not isinstance(retries, int) or retries not in (0, 1):
        raise RuntimeError("LLM_MAX_RETRIES must be 0 or 1.")
    if settings.LLM_EXTERNAL_PROCESSING_ENABLED and not (settings.SUBQ_API_KEY or "").strip():
        raise RuntimeError(
            "SUBQ_API_KEY is required when LLM_PROVIDER=subq and "
            "LLM_EXTERNAL_PROCESSING_ENABLED=true."
        )


def load_subq_config(settings: Any, *, require_key: bool) -> SubQConfig:
    validate_provider_settings(settings)
    if (settings.LLM_PROVIDER or "").strip().lower() != "subq":
        raise ConfigurationError("provider_not_subq")
    key = (settings.SUBQ_API_KEY or "").strip()
    if require_key and not key:
        raise ConfigurationError("missing_api_key")
    return SubQConfig(
        api_key=key,
        base_url=normalize_subq_base_url(settings.SUBQ_BASE_URL),
        model=settings.SUBQ_MODEL.strip(),
        timeout_seconds=float(settings.LLM_TIMEOUT_SECONDS),
        max_output_tokens=int(settings.LLM_MAX_OUTPUT_TOKENS),
        max_retries=int(settings.LLM_MAX_RETRIES),
    )


def public_llm_status() -> dict:
    """Non-secret capability flags for /health. Live generation is not claimed here."""
    from app.core.config import settings

    provider = settings.LLM_PROVIDER if settings.LLM_PROVIDER in ("none", "subq") else "none"
    return {
        "provider": provider,
        "external_processing_enabled": bool(settings.LLM_EXTERNAL_PROCESSING_ENABLED),
        "model": settings.SUBQ_MODEL if provider == "subq" else None,
        "credentials_configured": bool((settings.SUBQ_API_KEY or "").strip()) if provider == "subq" else False,
        "live_generation": "unverified",
    }
