"""SubQ is the only text-generation provider wired in this phase."""

from __future__ import annotations

from app.services.llm.providers.subq import SubQProvider
from app.services.llm.schemas import Completion


def complete(messages: list[dict], *, allow_live: bool = False) -> Completion:
    """Stateless completion with the configured provider. ``none`` has no client."""
    return SubQProvider.from_settings(allow_live=allow_live).complete(messages)
