"""Validation shared by saved and simulated holdings."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from fastapi import HTTPException

from app.services.governance.rules import to_decimal


def validate_holdings_set(tickers: Iterable[str], weights: Iterable[float]) -> None:
    """
    Enforces Gripper's portfolio model: long-only and unleveraged.
    Each weight is a fraction of portfolio value in [0, 1] (checked by the request
    schema), tickers are unique (case-insensitive), and weights sum to at most 1
    exactly (decimal arithmetic, no tolerance). The remainder is implicit cash.
    Short positions, leverage and derivatives are out of scope by design; this is a
    product assumption, not a general investment constraint (docs/COMPLIANCE_MODEL.md).
    """
    upper = [t.upper() for t in tickers]
    if len(set(upper)) != len(upper):
        raise HTTPException(status_code=422, detail="Duplicate tickers in holdings.")
    if sum((to_decimal(w) for w in weights), Decimal(0)) > 1:
        raise HTTPException(
            status_code=422,
            detail="Total holdings weight exceeds 100%. Gripper supports long-only, unleveraged portfolios.",
        )
