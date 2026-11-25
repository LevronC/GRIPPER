"""
Opt-in SubQ access check. Does not send portfolio data or research.

Exit codes:
  0  configured model is listed; with generate=True, one synthetic completion succeeded
  2  configuration or credentials
  3  configured text model is not available to this key
  4  the synthetic generation failed
  5  the account has no credits
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.services.llm.config import load_subq_config
from app.services.llm.errors import (
    AuthenticationError,
    ConfigurationError,
    InsufficientCreditsError,
    LLMError,
    ModelAccessDeniedError,
)
from app.services.llm.providers.subq import SubQProvider

SYNTHETIC_USER_MESSAGE = (
    "Reply with the single word ready. This is a synthetic connectivity check with no customer data."
)
SYNTHETIC_MAX_TOKENS = 64


def synthetic_messages() -> list[dict[str, str]]:
    return [{"role": "user", "content": SYNTHETIC_USER_MESSAGE}]


def run_preflight(
    *,
    generate: bool = False,
    transport: httpx.BaseTransport | None = None,
    allow_live: bool = False,
) -> int:
    if settings.LLM_PROVIDER != "subq":
        print(
            "LLM_PROVIDER is not subq, so the API is serving deterministic explanations "
            "and this command will not call SubQ.\n"
            "To check access, run it with LLM_PROVIDER=subq and SUBQ_API_KEY set in the "
            "environment. Leave LLM_EXTERNAL_PROCESSING_ENABLED=false until excerpts "
            "should actually be sent."
        )
        return 2
    try:
        config = load_subq_config(settings, require_key=True)
    except (ConfigurationError, RuntimeError) as exc:
        code = getattr(exc, "code", None) or "invalid_configuration"
        print(f"SubQ configuration is not usable ({code}). No request was sent.")
        return 2

    provider = SubQProvider(config, transport=transport, allow_live=allow_live)
    # The synthetic call uses a smaller output cap than the application. Build a
    # second provider so the models check and the generation check stay separate.
    print(f"SubQ base URL: {config.base_url}")
    print(f"Configured model: {config.model}")
    print("External processing flag: " + ("enabled" if settings.LLM_EXTERNAL_PROCESSING_ENABLED else "disabled"))
    print("Request: GET /v1/models")
    try:
        model_ids = provider.list_models()
    except AuthenticationError:
        print("SubQ rejected the API key (401 invalid_api_key). Live text generation: UNVERIFIED.")
        return 2
    except InsufficientCreditsError:
        print("SubQ reported insufficient credits (402). Live text generation: UNVERIFIED.")
        return 5
    except ModelAccessDeniedError:
        print("SubQ denied model listing (403 model_not_allowed). Live text generation: UNVERIFIED.")
        return 3
    except LLMError as exc:
        print(f"SubQ models request failed ({exc.code}). Live text generation: UNVERIFIED.")
        return 4

    print("Models visible to this key: " + (", ".join(model_ids) if model_ids else "(none)"))
    if config.model not in model_ids:
        snap = "subq-snap-1.2" in model_ids
        print(
            f"{config.model} is not available to this key. "
            "SubQ Savant requires early-access authorization for the organization.\n"
            "No other provider was called. SubQ Snap is a decision model and was not used "
            "to generate text."
            + (" Snap is listed for this key; that does not enable explanation generation." if snap else "")
            + "\nDeterministic explanations remain in effect. Live text generation: UNVERIFIED."
        )
        return 3
    print(f"{config.model} is listed for this key.")
    if not generate:
        print("No chat completion was sent. Pass --generate to send one synthetic request.")
        return 0

    print(
        "Request: POST /v1/chat/completions "
        f"(1 call, max_tokens={SYNTHETIC_MAX_TOKENS}, store=false, no customer data)"
    )
    narrow = SubQProvider(
        _with_token_cap(config, SYNTHETIC_MAX_TOKENS),
        transport=transport,
        allow_live=allow_live,
    )
    try:
        completion = narrow.complete_text(synthetic_messages())
    except InsufficientCreditsError:
        print("Synthetic generation was refused: insufficient credits (402). Live text generation: UNVERIFIED.")
        return 5
    except ModelAccessDeniedError:
        print(
            "Synthetic generation was refused: model_not_allowed (403). "
            "Listing the model did not grant a completion. Live text generation: UNVERIFIED."
        )
        return 3
    except AuthenticationError:
        print("Synthetic generation was refused: invalid API key (401). Live text generation: UNVERIFIED.")
        return 2
    except LLMError as exc:
        print(f"Synthetic generation failed ({exc.code}). Live text generation: UNVERIFIED.")
        return 4
    preview = completion.content.replace("\n", " ")[:200]
    print(
        f"Synthetic completion received ({len(completion.content)} chars, "
        f"attempts={completion.attempts}). Preview: {preview}"
    )
    return 0


def synthetic_request_body(model: str) -> dict[str, Any]:
    """The payload --generate sends. No schema, no tools, no customer data."""
    from app.services.llm.config import REASONING_EFFORT

    return {
        "model": model,
        "messages": synthetic_messages(),
        "max_tokens": SYNTHETIC_MAX_TOKENS,
        "reasoning_effort": REASONING_EFFORT,
        "store": False,
    }


def _with_token_cap(config: Any, max_tokens: int) -> Any:
    return type(config)(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        timeout_seconds=config.timeout_seconds,
        max_output_tokens=max_tokens,
        max_retries=0,
        retry_backoff_seconds=0,
    )
