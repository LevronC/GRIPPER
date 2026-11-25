"""Request and response shapes for explanation generation.

The JSON Schema is sent to the provider. The Pydantic model is the local check
and is the one Gripper trusts. Provider-side schema enforcement is not sufficient.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_restatement: str = Field(min_length=1, max_length=2_000)
    research_commentary: str = Field(min_length=1, max_length=4_000)
    cited_chunk_ids: list[str] = Field(max_length=8)
    insufficient_research: bool


# SubQ Chat Completions structured outputs: root object, every property required,
# additionalProperties false. Kept hand-written so the request does not pick up
# Pydantic's title/$defs keys.
EXPLANATION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "policy_restatement",
        "research_commentary",
        "cited_chunk_ids",
        "insufficient_research",
    ],
    "properties": {
        "policy_restatement": {"type": "string"},
        "research_commentary": {"type": "string"},
        "cited_chunk_ids": {"type": "array", "items": {"type": "string"}},
        "insufficient_research": {"type": "boolean"},
    },
}

RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "gripper_violation_explanation",
        "strict": True,
        "schema": EXPLANATION_JSON_SCHEMA,
    },
}


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None


class Completion(BaseModel):
    """Provider answer. Reasoning text is never copied onto this object."""

    model_config = ConfigDict(extra="forbid")

    content: str
    model: str | None
    usage: TokenUsage
    latency_ms: float
    attempts: int
